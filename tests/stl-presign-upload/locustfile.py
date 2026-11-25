"""
Load test: STL presigned upload through the Linode assets proxy (sandbox).

Each Locust user acts like one designer dropping files on Design Export.
For every file it does what Stackboard does:
  1. generatePresignedUploadUrl  (GraphQL, gateway)
  2. PUT the file                (Linode assets proxy -> bucket)
  3. createAssetFromKey          (GraphQL, gateway)
It uploads 3 files at a time (same as Stackboard). After its batches
("batches-per-user", default 1) the user stays idle until the test is stopped.

Settings are in the dashboard under "Custom parameters". Type the token into
the form for each run. Do not put it in the Docker command or environment:
values given at startup can be read in the dashboard page source.

The upload link is sent through the proxy the same way the frontend does it:
when the backend returns a *.linodeobjects.com address, the host is swapped
for "proxy-endpoint". So the proxy is tested whether or not the backend
already returns the proxy address itself.

Everything is uploaded under resource key "loadtest_presign|file_asset_id":
files land in the bucket under "loadtest-presign/file/...", and the asset
rows have that resource key. Nothing is deleted automatically.
"""

import os
import re
import time
import uuid
from urllib.parse import urlsplit

import gevent
from gevent.pool import Pool
from locust import HttpUser, constant, events, task

STL_MIME_TYPE = "model/stl"
RESOURCE_KEY = "loadtest_presign|file_asset_id"

# (connect, no progress) in seconds. Without these a hung request waits
# forever and is never counted as a failure.
GRAPHQL_TIMEOUT = (10, 60)
UPLOAD_TIMEOUT = (10, 120)
IDLE_SECONDS = 5

PRESIGN_MUTATION = """
mutation GeneratePresignedUploadUrl($input: GeneratePresignedUploadUrlInput!) {
  generatePresignedUploadUrl(input: $input) { uploadUrl key expiresIn }
}
"""

CREATE_ASSET_MUTATION = """
mutation CreateAsset($input: CreateAssetFromKeyInput!) {
  createAssetFromKey(input: $input) { id name size }
}
"""


@events.init_command_line_parser.add_listener
def _(parser):
    token_help = "Bearer token: localStorage.getItem('rata.token') on sandbox Stackboard"
    try:
        parser.add_argument("--rata-token", type=str, default="", is_secret=True, help=token_help)
    except TypeError:  # Locust version without is_secret
        parser.add_argument("--rata-token", type=str, default="", help=token_help)
    # Number defaults are written as floats on purpose: the dashboard converts
    # what you type with the type of the default, so 16 would refuse "0.5".
    parser.add_argument("--file-mb", type=float, default=16.0,
                        help="Size of each uploaded file in MB")
    parser.add_argument("--files-per-batch", type=int, default=60,
                        help="Files in one batch (one Design Export drop)")
    parser.add_argument("--batches-per-user", type=int, default=1,
                        help="Batches each user uploads, then it stays idle (0 = repeat until stopped)")
    parser.add_argument("--parallel", type=int, default=3,
                        help="Files uploaded at the same time per user (Stackboard uses 3)")
    parser.add_argument("--wait-seconds", type=float, default=10.0,
                        help="Pause between two batches of the same user")
    parser.add_argument("--proxy-endpoint", type=str, default="https://proxy-sandbox-dynamic.rata.id",
                        help="Linode assets proxy. A *.linodeobjects.com upload link is sent here, like the frontend does")


# One random buffer per size, shared by all users (keeps memory low).
_payloads = {}


def payload(size_mb):
    size = max(0, int(size_mb * 1024 * 1024))
    if size not in _payloads:
        _payloads[size] = os.urandom(size)
    return _payloads[size]


def upload_target(upload_url, proxy_endpoint):
    """Where the file is PUT, and a label for the results row.

    Same rule as the frontend: a *.linodeobjects.com link goes to the proxy,
    with the same path and signed query.
    """
    parts = urlsplit(upload_url)
    is_linode = (parts.hostname or "").endswith(".linodeobjects.com")
    proxy = (proxy_endpoint or "").strip().rstrip("/")
    if is_linode and proxy:
        query = f"?{parts.query}" if parts.query else ""
        return f"{proxy}{parts.path}{query}", "proxy"
    if is_linode:
        return upload_url, "direct to Linode"
    return upload_url, "proxy"


def short_body(text):
    """Stable summary of an error body: the storage error code or the page title."""
    text = text or ""
    code = re.search(r"<Code>([^<]*)</Code>", text)
    if code:
        return code.group(1)
    title = re.search(r"<title>([^<]*)</title>", text, re.IGNORECASE)
    if title:
        return title.group(1).strip()
    return re.sub(r"\s+", " ", text).strip()[:80]


def failure_reason(res):
    """Why a request failed, without its URL (the upload URL holds the signed query)."""
    error = getattr(res, "error", None)
    if res.status_code == 0 and error is not None:
        # No answer at all: name the error and its underlying cause.
        cause = error
        for _ in range(5):
            inner = getattr(cause, "reason", None)
            if not isinstance(inner, BaseException):
                inner = next((a for a in getattr(cause, "args", ()) if isinstance(a, BaseException)), None)
            if inner is None:
                break
            cause = inner
        kinds = type(error).__name__
        if cause is not error:
            kinds += f" ({type(cause).__name__})"
        return f"no response: {kinds}"
    return f"status {res.status_code}: {short_body(res.text)}"


class StlPresignUploadUser(HttpUser):
    # No host here: the target is the Host field on the start form (sandbox: https://gateway-sandbox-dynamic.rata.id).
    # Pauses are handled in the task (wait-seconds, and idle when done).
    wait_time = constant(0)

    def on_start(self):
        self.opts = self.environment.parsed_options
        self.batches_done = 0
        self.pool = None
        token = (self.opts.rata_token or "").strip()
        self.auth = {"Authorization": f"Bearer {token}"}
        self.ready = bool(token)
        if not self.ready:
            # Show it on the results page (Failures tab). The user then stays idle.
            self.environment.events.request.fire(
                request_type="SETUP",
                name="token missing",
                response_time=0,
                response_length=0,
                exception=RuntimeError('Paste a token into "rata-token" (Custom parameters) and start again'),
                context={},
            )

    def on_stop(self):
        # Locust stops the user itself; also stop its uploads that are still running.
        if self.pool is not None:
            self.pool.kill()

    def gql(self, name, query, variables, field):
        """POST a GraphQL mutation. Returns data[field], or None after recording the failure."""
        with self.client.post(
            "/graphql",
            json={"query": query, "variables": variables},
            headers=self.auth,
            name=name,
            timeout=GRAPHQL_TIMEOUT,
            catch_response=True,
        ) as res:
            if res.status_code != 200:
                res.failure(failure_reason(res))
                return None
            try:
                body = res.json()
            except ValueError:
                res.failure(f"status 200, not JSON: {short_body(res.text)}")
                return None
            if not isinstance(body, dict):
                res.failure("status 200, unexpected answer")
                return None
            errors = body.get("errors")
            if errors:
                res.failure(str(errors[0].get("message"))[:200])
                return None
            value = (body.get("data") or {}).get(field)
            if not value:
                res.failure(f"no {field} in the answer")
                return None
            res.success()
            return value

    def upload_one(self, index, total):
        """Upload one file (all 3 steps). Returns True when its asset was created."""
        file_name = f"loadtest-{uuid.uuid4().hex[:8]}-stage_{index:02d}_of_{total - 1:02d}_upper.stl"

        presigned = self.gql(
            "1 generatePresignedUploadUrl",
            PRESIGN_MUTATION,
            {"input": {"resourceKey": RESOURCE_KEY, "fileName": file_name,
                       "mimeType": STL_MIME_TYPE}},
            "generatePresignedUploadUrl",
        )
        if not presigned:
            return False

        url, route = upload_target(presigned["uploadUrl"], self.opts.proxy_endpoint)
        # Absolute URL, and no Authorization header: the link itself is the permission.
        with self.client.put(
            url,
            data=payload(self.opts.file_mb),
            headers={"Content-Type": STL_MIME_TYPE},
            name=f"2 PUT {route} ({self.opts.file_mb:g} MB)",
            timeout=UPLOAD_TIMEOUT,
            catch_response=True,
        ) as res:
            if res.status_code != 200:
                res.failure(failure_reason(res))
                return False
            res.success()

        asset = self.gql(
            "3 createAssetFromKey",
            CREATE_ASSET_MUTATION,
            {"input": {"key": presigned["key"], "resourceKey": RESOURCE_KEY}},
            "createAssetFromKey",
        )
        return bool(asset)

    @task
    def upload_batch(self):
        limit = self.opts.batches_per_user
        if not self.ready or (limit and self.batches_done >= limit):
            # Nothing (more) to do: stay idle until the test is stopped.
            gevent.sleep(IDLE_SECONDS)
            return

        total = max(1, self.opts.files_per_batch)
        started = time.time()
        self.pool = Pool(max(1, self.opts.parallel))
        jobs = [self.pool.spawn(self.upload_one, i, total) for i in range(total)]
        self.pool.join()
        failed = sum(1 for job in jobs if not job.value)
        self.batches_done += 1

        # One row per batch: the time a designer waits for one drop. In the real
        # app a batch with any failed file is not handed to Design Export at all.
        self.environment.events.request.fire(
            request_type="BATCH",
            name=f"batch of {total} files",
            response_time=(time.time() - started) * 1000,
            response_length=0,
            exception=RuntimeError(f"{failed} of {total} files failed") if failed else None,
            context={},
        )

        if not limit or self.batches_done < limit:
            gevent.sleep(self.opts.wait_seconds)

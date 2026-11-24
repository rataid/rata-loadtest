"""
Dry run for locustfile.py: runs the test against a fake gateway + proxy on
127.0.0.1. Nothing is sent to sandbox or any real service.

Run it with the repo tool (inside the official Locust image, no local Python needed):
    .\\tools\\dryrun.ps1 -Test stl-presign-upload      (Windows)
    ./tools/dryrun.sh stl-presign-upload             (macOS / Linux)
or directly:
    python _dryrun_test.py              all scenarios
    python _dryrun_test.py stop hang    only these scenarios

The fake server is this same file started in "--serve" mode in a separate
process, so it runs without Locust's gevent patching.
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
LOCUSTFILE = os.path.join(HERE, "locustfile.py")


# ---------------------------------------------------------------- fake server

def serve(port, mode, lifetime, put_delay):
    """Fake gateway (GraphQL POST) and proxy (PUT). GET /__state returns what it saw."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    state = {"running": 0, "max": 0, "puts": 0, "presign": 0, "assets": 0, "gql": 0,
             "auth_on_put": 0, "auth_missing_on_gql": 0, "ctype": [],
             "put_path_ok": 0, "put_query_ok": 0}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def send(self, status, body, ctype="application/json"):
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.send(200, json.dumps(state) if self.path == "/__state" else "ok")

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                state["gql"] += 1
                if not self.headers.get("Authorization", "").startswith("Bearer "):
                    state["auth_missing_on_gql"] += 1
            if mode == "gw502":
                self.send(502, "<html><head><title>502 Bad Gateway</title></head></html>", "text/html")
                return
            if mode == "unauth":
                self.send(200, json.dumps({"errors": [{"message": "Unauthorized"}], "data": None}))
                return
            inp = body["variables"]["input"]
            if "generatePresignedUploadUrl" in body["query"]:
                with lock:
                    state["presign"] += 1
                name = inp["fileName"]
                query = f"X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=sig-{name}"
                path = f"/loadtest-presign/file/a/b/c/{name}"
                if mode == "linode":
                    url = f"https://assets-dynamic-dev.sg-sin-1.linodeobjects.com{path}?{query}"
                elif mode == "refuse":
                    url = f"http://127.0.0.1:1{path}?{query}"
                else:
                    url = f"http://127.0.0.1:{port}{path}?{query}"
                self.send(200, json.dumps({"data": {"generatePresignedUploadUrl":
                                                    {"uploadUrl": url, "key": path[1:], "expiresIn": 300}}}))
            else:
                with lock:
                    state["assets"] += 1
                asset = None if mode == "assetnull" else {"id": "a1", "name": "n", "size": 1}
                self.send(200, json.dumps({"data": {"createAssetFromKey": asset}}))

        def do_PUT(self):
            with lock:
                state["running"] += 1
                state["max"] = max(state["max"], state["running"])
                if self.headers.get("Authorization"):
                    state["auth_on_put"] += 1
                ctype = self.headers.get("Content-Type")
                if ctype not in state["ctype"]:
                    state["ctype"].append(ctype)
            self.rfile.read(int(self.headers["Content-Length"]))
            path, _, query = self.path.partition("?")
            name = path.rsplit("/", 1)[-1]
            with lock:
                state["put_path_ok"] += path.startswith("/loadtest-presign/file/a/b/c/")
                state["put_query_ok"] += query == f"X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=sig-{name}"
            time.sleep(20 if mode == "hang" else put_delay)
            with lock:
                state["running"] -= 1
                state["puts"] += 1
            stage = re.search(r"stage_(\d+)_", name)
            if mode == "put403" and stage and int(stage.group(1)) % 2 == 1:
                rid = uuid.uuid4().hex
                self.send(403, f"<Error><Code>AccessDenied</Code><RequestId>tx{rid}</RequestId></Error>",
                          "application/xml")
            else:
                self.send(200, "")

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            # The client hanging up mid-upload (Stop, timeouts) is expected here
            if not isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
                super().handle_error(request, client_address)

    server = Server(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(lifetime)


# ---------------------------------------------------------------- scenarios

def main(only):
    import types
    import importlib.util

    import gevent
    from locust.argument_parser import get_parser
    from locust.env import Environment

    spec = importlib.util.spec_from_file_location("locustfile_under_test", LOCUSTFILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    failures = []

    def check(name, ok, detail=""):
        print(f"   {'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if detail and not ok else ""))
        if not ok:
            failures.append(name)

    def fetch_state(base):
        return json.loads(urllib.request.urlopen(base + "/__state", timeout=5).read().decode())

    def snapshot(env):
        rows = {f"{e.method} {e.name}": (e.num_requests, e.num_failures) for e in env.stats.entries.values()}
        errors = {f"{e.method} {e.name} :: {e.error}": e.occurrences for e in env.stats.errors.values()}
        return rows, errors

    def count(rows, prefix):
        return next((v for k, v in rows.items() if k.startswith(prefix)), (0, 0))

    def run(mode, port, users, seconds, settings=(), put_delay=0.1, patch=None, stop_at=None, after_stop=0.0):
        server = subprocess.Popen([sys.executable, __file__, "--serve", str(port), mode, "90", str(put_delay)])
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(50):
                try:
                    fetch_state(base)
                    break
                except Exception:
                    time.sleep(0.2)
            values = {"--file-mb": "0.2", "--files-per-batch": "6", "--parallel": "3", "--wait-seconds": "0.3",
                      "--rata-token": "tok", "--proxy-endpoint": base}
            values.update(dict(zip(settings[::2], settings[1::2])))
            args = ["-f", LOCUSTFILE, "--host", base]
            for key, value in values.items():
                args += [key, value]
            opts = get_parser().parse_args(args=args)
            env = Environment(user_classes=[mod.DesignExportUser], host=base, parsed_options=opts)
            runner = env.create_local_runner()
            saved = {k: getattr(mod, k) for k in (patch or {})}
            for key, value in (patch or {}).items():
                setattr(mod, key, value)
            runner.start(users, spawn_rate=users)
            result = types.SimpleNamespace()
            if stop_at is not None:
                gevent.sleep(stop_at)
                runner.stop()
                result.at_stop = snapshot(env)
                gevent.sleep(after_stop)
                result.later = snapshot(env)
            else:
                gevent.sleep(seconds)
                runner.stop()
            result.rows, result.errors = snapshot(env)
            result.state = fetch_state(base)
            runner.quit()
            for key, value in saved.items():
                setattr(mod, key, value)
            return result
        finally:
            server.terminate()

    scenarios = []

    def scenario(fn):
        scenarios.append(fn)
        return fn

    @scenario
    def helpers():
        """pure helper functions"""
        t = mod.upload_target
        link = "https://assets-dynamic-dev.sg-sin-1.linodeobjects.com/a/b/c.stl?X-Amz-Signature=s&x=1"
        check("Linode link is sent to the proxy, same path and query",
              t(link, "https://proxy.test") == ("https://proxy.test/a/b/c.stl?X-Amz-Signature=s&x=1", "proxy"))
        check("proxy with trailing slash gives no double slash",
              t(link, "https://proxy.test/")[0] == "https://proxy.test/a/b/c.stl?X-Amz-Signature=s&x=1")
        check("empty proxy keeps the Linode link, labelled 'direct to Linode'", t(link, "") == (link, "direct to Linode"))
        already = "https://proxy-sandbox-dynamic.rata.id/a/b/c.stl?X-Amz-Signature=s"
        check("a link that is already the proxy is kept", t(already, "https://proxy.test") == (already, "proxy"))
        xml = "<Error><Code>AccessDenied</Code><RequestId>tx123</RequestId></Error>"
        check("storage error is summarised as its code (no request id)", mod.short_body(xml) == "AccessDenied")
        check("error page is summarised as its title",
              mod.short_body("<html><head><title>413 Request Entity Too Large</title></head></html>")
              == "413 Request Entity Too Large")

    @scenario
    def one_batch():
        """2 users, 6 files each, 1 batch per user; the test keeps running after they finish"""
        r = run("ok", 8201, users=2, seconds=5)
        check("exactly 12 files uploaded", r.state["puts"] == 12, r.state["puts"])
        check("12 upload links, 12 assets", (r.state["presign"], r.state["assets"]) == (12, 12))
        check("12 uploads, 0 failures", count(r.rows, "PUT 2 PUT proxy") == (12, 0), r.rows)
        check("one batch row per user", count(r.rows, "BATCH batch of 6 files") == (2, 0), r.rows)
        check("never more than 3 uploads at a time per user", r.state["max"] <= 6, r.state["max"])
        check("token sent to the gateway only, never with the upload",
              (r.state["auth_missing_on_gql"], r.state["auth_on_put"]) == (0, 0))
        check("file type is model/stl", r.state["ctype"] == ["model/stl"], r.state["ctype"])
        check("no failures", not r.errors, r.errors)

    @scenario
    def two_batches():
        """batches-per-user 2"""
        r = run("ok", 8202, users=2, seconds=6, settings=("--batches-per-user", "2"))
        check("24 files and 4 batch rows", (r.state["puts"], count(r.rows, "BATCH")) == (24, (4, 0)),
              (r.state["puts"], r.rows))

    @scenario
    def unlimited():
        """batches-per-user 0 repeats until stopped"""
        r = run("ok", 8203, users=2, seconds=5, settings=("--batches-per-user", "0"))
        check("more than 2 batches ran", count(r.rows, "BATCH")[0] > 2, r.rows)

    @scenario
    def linode_link():
        """backend returns a *.linodeobjects.com link: it must go to the proxy"""
        r = run("linode", 8204, users=2, seconds=5)
        check("all 12 uploads arrived at the proxy", r.state["puts"] == 12, r.state["puts"])
        check("path and signed query unchanged", (r.state["put_path_ok"], r.state["put_query_ok"]) == (12, 12))

    @scenario
    def put_403():
        """every second file is rejected by storage"""
        r = run("put403", 8205, users=2, seconds=5)
        put_errors = {k: v for k, v in r.errors.items() if k.startswith("PUT ")}
        check("6 of 12 uploads failed", count(r.rows, "PUT 2 PUT proxy")[1] == 6, r.rows)
        check("one failure row without request ids",
              list(put_errors.items()) == [("PUT 2 PUT proxy (0.2 MB) :: status 403: AccessDenied", 6)], put_errors)
        check("no asset created for failed files", r.state["assets"] == 6, r.state["assets"])
        check("both batches reported as failed", count(r.rows, "BATCH") == (2, 2), r.rows)

    @scenario
    def hang():
        """the proxy never answers: the timeout turns it into a failure"""
        r = run("hang", 8206, users=1, seconds=5, settings=("--files-per-batch", "3"),
                patch={"UPLOAD_TIMEOUT": (2, 2)})
        put_errors = {k: v for k, v in r.errors.items() if k.startswith("PUT ")}
        check("3 uploads reported as failed", count(r.rows, "PUT 2 PUT proxy")[1] == 3, r.rows)
        check("reason names a timeout, without the URL",
              put_errors and all("no response:" in k and "Timeout" in k and "X-Amz" not in k for k in put_errors),
              put_errors)

    @scenario
    def refused():
        """connection refused"""
        r = run("refuse", 8207, users=1, seconds=7, settings=("--files-per-batch", "3"))
        put_errors = {k: v for k, v in r.errors.items() if k.startswith("PUT ")}
        check("one grouped reason, without the URL",
              len(put_errors) == 1 and all("no response: ConnectionError" in k and "X-Amz" not in k
                                           for k in put_errors), put_errors)

    @scenario
    def unauthorized():
        """expired or wrong token"""
        r = run("unauth", 8208, users=1, seconds=3)
        check("step 1 fails with the backend's message",
              r.errors.get("POST 1 generatePresignedUploadUrl :: Unauthorized") == 6, r.errors)
        check("nothing uploaded", r.state["puts"] == 0)

    @scenario
    def gateway_502():
        """gateway answers 502 with an error page"""
        r = run("gw502", 8209, users=1, seconds=3)
        check("status and page title shown",
              r.errors.get("POST 1 generatePresignedUploadUrl :: status 502: 502 Bad Gateway") == 6, r.errors)

    @scenario
    def asset_null():
        """createAssetFromKey answers null"""
        r = run("assetnull", 8210, users=1, seconds=3)
        check("step 3 counted as failed",
              r.errors.get("POST 3 createAssetFromKey :: no createAssetFromKey in the answer") == 6, r.errors)

    @scenario
    def no_token():
        """token field left empty"""
        r = run("ok", 8211, users=2, seconds=3, settings=("--rata-token", ""))
        setup = {k: v for k, v in r.errors.items() if k.startswith("SETUP ")}
        check("shown on the results page, once per user", list(setup.values()) == [2], setup)
        check("no request sent", r.state["gql"] == 0, r.state["gql"])

    @scenario
    def stop():
        """Stop pressed while uploads are running"""
        r = run("ok", 8212, users=2, seconds=0, settings=("--files-per-batch", "30"),
                put_delay=1.5, stop_at=2.2, after_stop=3.0)
        at_stop, later = count(r.at_stop[0], "PUT 2 PUT proxy")[0], count(r.later[0], "PUT 2 PUT proxy")[0]
        check("no upload finishes after Stop", later == at_stop, (at_stop, later))

    for fn in scenarios:
        if only and fn.__name__ not in only:
            continue
        print(f"\n[{fn.__name__}] {fn.__doc__}")
        fn()

    print("\n" + ("ALL PASSED" if not failures else f"{len(failures)} CHECK(S) FAILED: " + "; ".join(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        serve(int(sys.argv[2]), sys.argv[3], float(sys.argv[4]), float(sys.argv[5]))
    else:
        sys.exit(main(set(sys.argv[1:])))

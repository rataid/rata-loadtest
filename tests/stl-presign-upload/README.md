# Locust load test: STL presigned upload (sandbox)

`locustfile.py` simulates designers dropping STL files on Design Export after the presign change.
Each Locust user does what Stackboard does for every file:

1. `generatePresignedUploadUrl` (GraphQL, gateway → `base`)
2. `PUT` the file to the upload link (Linode assets proxy → bucket)
3. `createAssetFromKey` (GraphQL, gateway → `base`)

A user uploads one batch of files, 3 at a time (same as Stackboard), and then stays idle.
The files are random bytes, not real STL. That's enough for the upload path, but there's no 3D preview.

The upload always goes through the proxy. If the backend returns a `*.linodeobjects.com` address
(sandbox does, until the backend PR is merged), the script sends it to the proxy the same way the frontend does.

## Before the test

- **Script:** once the VM is set up as in [vm/README.md](../../vm/README.md), it runs the latest `master` by itself. Until then, SRE puts `locustfile.py` into the Locust Docker container; ask them again whenever the script changes.
- **Only our script should run.** Under **User classes** on the start form, tick only `DesignExportUser`. If another script is loaded without `--class-picker` (e.g. the old health-check script), both run together and `/app/live` requests mix into the results.
- **Where Locust runs:** a Docker container on a VM in Singapore, the same region as the Linode bucket (confirmed by SRE, 2026-11-20). It calls the public gateway and proxy, the same path as a browser. A small VM can still be the bottleneck: if uploads are slow but the proxy is calm in Grafana, check the VM's CPU and network.
- **Locust version:** the script was tested with 2.47. Ask SRE which version the VM runs.
- **Time slot:** agree on one with Kin (and anyone else load testing sandbox), so results don't mix.
- **Token:** on sandbox Stackboard, DevTools → Console → `localStorage.getItem('rata.token')`. Get it right before the test, because it expires. Type it into the Locust form only. Never put it in chat, in files, or in the Docker command or environment: values given at startup can be read in the dashboard page source.

## Start a case in the Locust dashboard

- **Host:** already filled in (`https://gateway-sandbox-dynamic.rata.id`).
- **Number of users / Ramp up:** see the table below.
- **Custom parameters:**

| Parameter | Value | Meaning |
|---|---|---|
| `rata-token` | your token | Bearer token for the GraphQL calls |
| `file-mb` | see table | Size of each file in MB |
| `files-per-batch` | 60 | Files in one batch (one Design Export drop) |
| `batches-per-user` | 1 | Batches each user uploads, then it stays idle. 0 = repeat until stopped |
| `parallel` | 3 | Files at the same time per user (Stackboard uses 3) |
| `wait-seconds` | 10 | Pause between two batches of the same user (only matters with more than 1 batch) |
| `proxy-endpoint` | `https://proxy-sandbox-dynamic.rata.id` | The proxy under test. Leave as is |

With `batches-per-user` 1, every user uploads its 60 files once. When the requests per second drop to 0, everyone is done: press **Stop**.

## Cases

Split as Kin suggested: many users with small files, and large files on their own.

| Case | Users | Ramp up | `file-mb` | Checks | Data uploaded |
|---|---|---|---|---|---|
| A. Many users at once | 20 | 2/s | 1 | Proxy and `base` with 20 users together | about 1.2 GB |
| B. Large files | 1 | 1/s | 16 | 16 MB files pass the proxy; time per file | about 1 GB |
| C. Full case | 5, then 10, then 20 | 1/s | 16 | The real situation | about 5 GB, 10 GB, 19 GB |

For C, run 5 users first, then 10, then 20, so you can see where it starts to break.
Write down the start and end time of every case.

## What to read in Locust

| Row | Meaning | Good |
|---|---|---|
| `1 generatePresignedUploadUrl` | Backend call that gives the upload link | Fast, no failures |
| `2 PUT proxy (… MB)` | The upload itself, through the proxy | 0 failures |
| `3 createAssetFromKey` | Backend call that records the asset | Fast, no failures |
| `batch of 60 files` | One whole drop: the time a designer waits | 0 failures; time stays steady as users increase |

- A batch counts as failed when any of its files failed. In the real app such a batch is not handed to Design Export at all, so this row is the one that matters most.
- Read the rows, not the **Aggregated** line: it also counts the batch rows.
- If row 2 says `direct to Linode` instead of `proxy`, the `proxy-endpoint` field was empty and the proxy was not tested.
- Check the **Failures** tab for the reasons, and download the report (Download Data) after each case.

### Failures and what they mean

| Failure | Cause |
|---|---|
| `token missing` | The token field was empty. Stop, paste a token, start again. |
| `Unauthorized` on steps 1 or 3 | Token expired or wrong. Get a new one and restart the case. |
| `status 413` on step 2 | File over the proxy limit (30 MB). Only happens if `file-mb` is above 30. |
| `status 403: AccessDenied` on step 2 | Storage refused the link: it expired before the upload started (links last 5 minutes), or the proxy changed the request. |
| `status 502` / `status 504` on step 2 | Proxy overloaded or timed out. This is what the test is looking for: note the case and the user count. |
| `no response: ReadTimeout …` | No answer for 2 minutes (1 minute for the backend calls). The request hung. |
| `no response: ConnectionError …` | The connection was refused or dropped. The name in brackets says which. |
| `status 429`, or `status 403` with a Cloudflare page title | Cloudflare is blocking the test traffic (all from one VM IP), not a server failure. Ask SRE to allow the VM's IP. |

## What to watch in Grafana

Find these services on sandbox before the test, and note their normal values for a few minutes before you start:

| Service | Watch | Bad sign |
|---|---|---|
| Linode assets proxy (`proxy-sandbox-dynamic`, nginx) | CPU, memory, network in, 5xx/413 | Memory keeps climbing, 502/504 |
| `base` | CPU, memory, pod restarts | A restart (crash), memory near its limit |
| `gateway` | CPU, request latency | Latency climbs as users increase |
| Database (if there is a dashboard) | Connections, slow queries | Connections near the limit |

The files no longer go through `base`; it only handles two small GraphQL calls per file.
If `base` stays flat while the proxy carries the load, that shows the presign change works.

For the report:
- Set the Grafana time range to the test window.
- Take one screenshot per case (A, B, C), next to the Locust results for that case.

## Rehearsal on your own machine

`run-local` at the repo root starts Locust in Docker with this test's script (Docker must be running):

```powershell
.\run-local.ps1 -Test stl-presign-upload        # Windows
```
```bash
TEST=stl-presign-upload ./run-local.sh          # macOS / Linux
```

Then open `http://localhost:8089`. Add `-Version <x.y.z>` (Windows) or `VERSION=<x.y.z>` (macOS/Linux) to run the
same Locust version as the VM.

A local run is only for checking that the token, the settings and the three steps work. Use small values:
1 user, `file-mb` 1, `files-per-batch` 3. It uploads 3 real test files to sandbox.
Don't run the real cases from a laptop: the 16 MB uploads would measure your internet, not the server.

## After the test

Everything uses resource key `loadtest_presign|file_asset_id`:
- **Bucket:** files are under `loadtest-presign/file/...` in `assets-dynamic-dev`.
- **Database:** asset rows have resource key `loadtest_presign|file_asset_id`.

Nothing is deleted automatically. All three cases together leave about 36 GB, so clean up afterwards: count the
objects under the prefix and the asset rows with that resource key, then delete both.

Save the Locust report and Grafana screenshots of each run in `results/` (e.g. `results/2026-11-24/`).

## Report template

| Case | Users | File size | Files uploaded | Failed files | Failed batches | Time per batch (p95) | Proxy (CPU / memory) | `base` | Notes |
|---|---|---|---|---|---|---|---|---|---|
| A | 20 | 1 MB | | | | | | | |
| B | 1 | 16 MB | | | | | | | |
| C | 5 / 10 / 20 | 16 MB | | | | | | | |

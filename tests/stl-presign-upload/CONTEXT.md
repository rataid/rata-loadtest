# Load test context: STL presigned upload

Filled-in example of `tests/_template/CONTEXT.md`. The script and README in this folder were written from it.

## 1. Goal

- **Question this test answers:** Can designers upload Design Export STL batches (60 × 16 MB) at the same time
  through presigned URLs and the Linode assets proxy, without failures, and without load on `base`?
- **Why now:** batches of 60 × 16 MB through the API (`base`) returned 502. STL uploads were moved to presigned URLs.
- **Ticket / PR:** stackboard #770 (frontend), rata-dynamic #965 (backend)

## 2. Flow under test

- **Code to test (repo + branch, or PR):** stackboard `feat/stl-presign-upload-dev` (#770), rata-dynamic
  `feat/stl-presign-upload-dev` (#965), base `dev`
- **Already deployed to the test environment?** Not yet when the test was written: sandbox still returned the raw
  Linode upload link (backend PR not merged), so the test sends `*.linodeobjects.com` links to the proxy itself,
  like the frontend does.
- **User action:** Aligner → Design → Rt. Export → drop 60 STL files on Design Export. Files upload 3 at a time.
  When all succeed, the files are attached to the design export.
- **Where in the frontend (stackboard):** `src/components/presign-url-upload/presign-upload.ts` (`presignUpload`,
  `presignUploadQueue`), `src/components/presign-url-upload/upload-presigned-url.ts` (the PUT),
  `src/components/upload-v2/components/queue.tsx` (Design Export queue)
- **Where in the backend (rata-dynamic):** `apps/base/src/upload/upload.resolver.ts`
  (`generatePresignedUploadUrl`, `createAssetFromKey`), `apps/base/src/upload/upload.service.ts`
- **Requests, in order (per file):**

| Step | Method | Host / endpoint | Operation / path | Auth | Notes |
|---|---|---|---|---|---|
| 1 | POST | gateway `/graphql` | `generatePresignedUploadUrl` (resourceKey, fileName, mimeType `model/stl`) | Bearer token | returns `uploadUrl`, `key`, `expiresIn` (300 s) |
| 2 | PUT | proxy (`proxy-sandbox-dynamic.rata.id`) | path + signed query from `uploadUrl` | none (the link is the permission) | body = file, `Content-Type: model/stl` |
| 3 | POST | gateway `/graphql` | `createAssetFromKey` (key, resourceKey) | Bearer token | returns the asset |

- **Anything the frontend changes before sending:** if `uploadUrl` is a `*.linodeobjects.com` address, the frontend
  swaps the host for the proxy (`VITE_LINODE_ASSETS_PROXY_ENDPOINT`), keeping path and query. Content-Type is always
  `model/stl` for STL.

## 3. Load model

| Item | Value | Source |
|---|---|---|
| Users at the same time (peak) | 20 (about 80 aligner design users in production; peak still to confirm) | Kin (from roles); Mbak Elita (PM) to confirm |
| Actions per user | 60 files per batch, 1 batch | Lead (design export estimate) |
| Parallel requests per user | 3 | Stackboard code (`PRESIGN_CONCURRENCY`) |
| Payload size | 16 MB per file (about 15–16 MB real) | Team |
| Think time between actions | 10 s between batches (only matters with more than 1 batch) | Kin |
| Repeat per user | once | Real use: one drop per designer |

- **Cases to run:** A: 20 users × 1 MB (many users at once). B: 1 user × 16 MB (large files). C: 5 → 10 → 20 users
  × 16 MB (full case).

## 4. Environment and limits

- **Environment:** sandbox
- **Base host (Locust "Host"):** `https://gateway-sandbox-dynamic.rata.id`
- **Other hosts the test calls:** `https://proxy-sandbox-dynamic.rata.id` (Linode assets proxy → bucket
  `assets-dynamic-dev`, region `sg-sin-1`)
- **Known limits:** proxy body size 30 MB per request (`413` above); Cloudflare rejects requests over 100 MB;
  upload links expire after 300 s (checked when the upload starts).
- **Auth:** sandbox Stackboard → DevTools → `localStorage.getItem('rata.token')`. It expires; get a fresh one per run.

## 5. Test data and cleanup

- **Label / prefix for created data:** resource key `loadtest_presign|file_asset_id`; file names start with
  `loadtest-`
- **What the test creates:** one bucket object and one asset row per file. A: about 1.2 GB, B: about 1 GB,
  C: about 5 + 10 + 19 GB.
- **How to clean up:** bucket prefix `loadtest-presign/file/` in `assets-dynamic-dev`; asset rows with resource key
  `loadtest_presign|file_asset_id`.

## 6. Pass / fail

- **Pass when:** 0 failed uploads and 0 failed batches in every case; time per batch steady as users increase;
  no `base` restarts.
- **What to watch in Grafana:** proxy (CPU, memory, network in, 5xx/413), `base` (CPU, memory, restarts),
  `gateway` (latency), database (connections).

## 7. People

- **Runs the Locust VM:** SRE
- **Time slot agreed with:** Kin (Irsyad)
- **Reviewer of the generated script:** <to fill>

# Load test context: <test name>

Fill this in before generating a test. Copy this folder to `tests/<test-name>/`, fill in every section, then run
`/new-loadtest tests/<test-name>/CONTEXT.md` in Claude Code.

Write "unknown" rather than guessing: the generator will ask, and unknown numbers must come from the team.
See `tests/stl-presign-upload/CONTEXT.md` for a filled-in example.

## 1. Goal

- **Question this test answers:** <e.g. "Can 20 designers upload 60 × 16 MB STL files at the same time without 502?">
- **Why now:** <incident, release, new feature>
- **Ticket / PR:** <links>

## 2. Flow under test

- **Code to test (repo + branch, or PR):** <e.g. stackboard `feat/x-dev`, rata-dynamic `feat/x-dev`; or `dev`>
- **Already deployed to the test environment?** <yes / no: which part is not yet>
- **User action:** <what a real user does, step by step, in the app>
- **Where in the frontend (stackboard):** <page / component paths>
- **Where in the backend (rata-dynamic):** <resolvers / services>
- **Requests, in order:**

| Step | Method | Host / endpoint | Operation / path | Auth | Notes |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |

- **Anything the frontend changes before sending** (host rewrites, headers, file type): <…>

## 3. Load model

Source of each number (PM, analytics, logs, team): fill in the last column.

| Item | Value | Source |
|---|---|---|
| Users at the same time (peak) | | |
| Actions per user (e.g. files per batch, requests) | | |
| Parallel requests per user | | |
| Payload size | | |
| Think time between actions | | |
| Repeat per user (once, or until stopped) | | |

- **Cases to run** (small → full): <e.g. A: 20 users small files, B: 1 user large files, C: 5 → 10 → 20 users full>

## 4. Environment and limits

- **Environment:** sandbox <change only if agreed>
- **Base host (Locust "Host"):** <e.g. https://gateway-sandbox-dynamic.rata.id>
- **Other hosts the test calls:** <e.g. proxy, storage>
- **Known limits:** <body size per request, Cloudflare 100 MB, timeouts, rate limits, link expiry>
- **Auth:** <how to get a token, how long it lasts>

## 5. Test data and cleanup

- **Label / prefix for created data:** <resource key, name prefix>
- **What the test creates:** <rows, files, approx. volume per case>
- **How to clean up:** <query / bucket prefix>

## 6. Pass / fail

- **Pass when:** <e.g. 0 failed uploads, p95 per batch under X s, no pod restarts>
- **What to watch in Grafana:** <services and panels>

## 7. People

- **Runs the Locust VM:** SRE
- **Time slot agreed with:** <names>
- **Reviewer of the generated script:** <name>

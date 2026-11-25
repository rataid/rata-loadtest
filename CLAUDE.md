# Writing a load test

Rules for new tests in this repo. They come from mistakes found while reviewing the first test
(`tests/stl-presign-upload`), which is the reference to copy from.

New tests start from a filled-in `tests/<name>/CONTEXT.md` (form: `tests/_template/CONTEXT.md`) and are generated
with the `/new-loadtest` command (`.claude/skills/new-loadtest/SKILL.md`).

## Before writing

Collect these facts (the context form asks for them); most can't be read from the code:
- **Which flow, and how the app really does it.** Read the frontend (stackboard) and backend (rata-dynamic) code for
  the exact requests, headers and order. The test must take the same path as a browser, including any proxy or
  host rewrite the frontend does. The first draft of the reference test skipped the proxy because the frontend's
  rewrite was missing.
- **Realistic numbers:** how many users at once, how many requests or files each, file sizes. Ask the PM (user
  counts) and the team; don't guess.
- **Limits** that cap the test, e.g. proxy body size, Cloudflare (100 MB per request), upload link expiry.
- **Environment:** sandbox unless agreed otherwise.

## Script rules

1. **One folder per test** under `tests/<test-name>/` with `locustfile.py`, `README.md` and `results/`.
2. **No `host` on the user class.** The target is typed into the Host field of the start form, so one field decides
   where every test goes (a class host only shows up as a confusing second Host in the ⚙ settings). Put the
   value to type in the test's README (e.g. `https://gateway-sandbox-dynamic.rata.id`).
3. **Token in the form only.** Add it as a custom parameter with `is_secret=True`. No env var, no default value,
   nothing in the Docker command.
4. **Settings as custom parameters** (`include_in_web_ui` is the default for parser arguments added in
   `init_command_line_parser`). Write number defaults with the right type: a float setting needs a float default
   (`16.0`), otherwise the dashboard refuses decimals.
5. **Bounded work per user.** Each user does a fixed amount (e.g. one batch) and then stays idle. Never loop
   forever by default: a 10-minute run with an endless loop created many times the planned data in the reference
   test. Make repeating an explicit option.
6. **Timeouts on every request** (connect and read). A hung request must become a failure, not wait forever.
7. **Failure reasons that group well:** status code plus a short stable summary (error code or page title).
   Never include the URL (presigned URLs contain signatures) or per-request ids (they split the Failures table).
   For "no response" errors, report the error type and its cause.
8. **Mark failures correctly:** use `catch_response=True`; a GraphQL `200` with `errors`, or with a missing/null
   result, is a failure.
9. **Show setup problems on the results page**, e.g. a missing token, via a failed `SETUP` request event, not only
   in the log.
10. **Stop means stop:** kill work the user started (e.g. a gevent pool) in `on_stop`.
11. **Name rows by step** (`1 …`, `2 …`) so the results read in order. Add one summary row per user action
    (e.g. a batch) if that's what the user experiences; don't add a row per request that doubles the totals.
12. **Test data is labelled** with its own resource key / name prefix so it can be found and deleted.
13. **Send credentials only where needed:** the token goes to the gateway, never to storage or a proxy.
14. **Works next to the other tests.** The VM loads every test at once (`locust -f tests/ --class-picker`, see
    `vm/README.md`), so:
    - only `locustfile.py` may be a plain name: any other `.py` file under `tests/` starts with `_`
      (`_dryrun_test.py`, `_helpers.py`), or Locust imports it as a test;
    - the user class is named after the test folder in PascalCase plus `User` (`stl-presign-upload` →
      `StlPresignUploadUser`): it is the name shown in the dashboard picker, and it stays unique;
    - custom parameter names don't clash with another test's: check the existing tests before adding one. Locust
      fails at startup on a duplicate, and the VM then keeps the old version;
    - no code at module level that does work (requests, file writes): importing the file must be harmless.

## README for each test

Copy the structure of `tests/stl-presign-upload/README.md`:
- what the test does and which requests it sends;
- before the test (script on the VM, `--class-picker`, time slot, token);
- dashboard settings table and the cases (users, ramp up, values, expected data volume);
- how to read each row, and a table of failures and their causes;
- what to watch in Grafana;
- local rehearsal;
- cleanup of test data;
- report template.

## Check before anyone runs it

1. **Dry run against a fake local server** (no real traffic), sized to the risk:
   - **Required** when the test writes anything (creates or changes records, uploads files) or sends large
     payloads: a mistake there leaves data behind or overloads a service. Add a `_dryrun_test.py` (copy the
     reference's `--serve` pattern) covering success, each failure type, timeouts, a missing token, Stop, and that
     the per-user limit holds.
   - **Optional** for read-only tests (only GET or read queries): steps 2 and 3 below are enough.

   Run it with `.\tools\dryrun.ps1 -Test <name>` (Windows) or `./tools/dryrun.sh <name>` (macOS/Linux): it runs
   inside the Locust image with networking off.
2. **Load it in the same Locust version as the VM** (`.\run-local.ps1 -Version <x.y.z>` on Windows,
   `VERSION=<x.y.z> ./run-local.sh` on macOS/Linux) and check every setting
   appears on the start form. Also check it loads together with the other tests, as on the VM:
   `docker run --rm -v "<repo>/tests:/t" locustio/locust:<x.y.z> -f /t --list` must list every test's user class.
3. **Rehearse locally** against sandbox with 1 user and small values.
4. **Review:** someone other than the author checks how much data the test creates and how hard it hits each
   service.

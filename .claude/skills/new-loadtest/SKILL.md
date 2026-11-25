---
name: new-loadtest
description: Create a Locust load test in the rata-loadtest repo. Interviews the user about what to test (or reads a filled-in tests/<name>/CONTEXT.md), writes CONTEXT.md, then generates locustfile.py, README.md and _dryrun_test.py and dry-runs them. Use when someone asks to create, generate or write a new load test.
---

# Create a load test

Two ways to start:
- `/new-loadtest` with no argument: **interview** the user, write `tests/<name>/CONTEXT.md` from the answers, then
  generate. This is the normal way.
- `/new-loadtest tests/<name>/CONTEXT.md`: the form is already filled in. Skip to step 3 (and still ask about
  anything missing).

Always read `CLAUDE.md` (the rules) and the reference test `tests/stl-presign-upload/` (`CONTEXT.md`,
`locustfile.py`, `README.md`, `_dryrun_test.py`) before writing anything.

## 1. Interview

Ask in short rounds, a few questions at a time, in the user's language. Use plain words; offer examples and a
suggested default where the team has one. Don't ask what you can find in the code yourself.

**Round 1: where the change is, what and why**
- Which repo(s) and branch(es) hold the code to test? A PR link also works. One per repo involved, e.g.
  `stackboard feat/stl-presign-upload-dev` and `rata-dynamic feat/stl-presign-upload-dev`. If there is no branch
  (testing existing behavior), use `dev`.
- In one sentence, which user action should be load tested? (A branch can touch several flows; this picks one.)
- What question should the test answer, and why now (incident, release, new feature)?

Then **find the flow in the code** before asking more. The repos are next to this one in the workspace
(`../stackboard`, `../rata-dynamic`); if one is missing, ask for its path.
- Read the branch **without switching the user's checkout** (they may have local work there):
  `git -C ../<repo> fetch origin <branch>`, then `git -C ../<repo> diff origin/<base>...origin/<branch>` to see what
  changed, and `git -C ../<repo> show origin/<branch>:<path>` to read files on that branch. The base is usually
  `dev` (ask if unsure). Never run checkout, switch, reset, stash or pull in those repos.
- If `git fetch` fails (no access), ask the user to fetch it themselves or to paste the relevant files.
- From the branch, locate the page/component of that user action and the requests it sends: order, operation names,
  inputs, the fields read from each answer, headers and content types, host rewrites or parallel limits in the
  frontend, and which requests need the token.
- Note anything the branch changes that is not yet on the environment under test (e.g. a backend change not yet
  deployed to sandbox), because the test must work against what is actually deployed.
- Show the user the request list you found and ask them to confirm it is the flow they mean.

**Round 2: load numbers** (each needs a source)
- How many users do this at the same time at peak? Who said so (PM, logs, team)?
- How much does one user do per action (files, requests, payload size)?
- Does a user do it once, or repeatedly? Any pause between actions?
- Which cases to run, small to full? Suggest a split like the reference (many users with small payloads, one user
  with large payloads, then the full case step by step).
If the user doesn't know a number, write "unknown" and say who could answer (the PM for user counts).
Don't make numbers up.

**Round 3: environment, data and pass/fail**
- Environment: sandbox, unless they explicitly want another (then confirm with them twice and note who agreed).
- Known limits: body size, Cloudflare (100 MB per request), rate limits, timeouts, link expiry.
- What data the test creates, and the label/prefix to use so it can be cleaned up (suggest one).
- What counts as a pass, and which services to watch in Grafana.
- Who reviews the script, and who to agree the time slot with.

## 2. Write CONTEXT.md and confirm

- Pick a folder name (kebab-case, e.g. `customer-file-upload`) and confirm it.
- Write `tests/<name>/CONTEXT.md` with the same sections as `tests/_template/CONTEXT.md`, filled from the answers
  and the code.
- Show a short summary: the requests per user action, the cases with their estimated load and data volume, the
  test-data label, and anything still "unknown".
- Ask: "Generate the test from this?" Wait for a yes. If numbers are still unknown, the user may still go ahead;
  note them as assumptions.

## 3. Check the context against the code

If the context came as an argument, read it and the code as in step 1. Stop and ask when:
- a field is "unknown", empty, or still `<…>`;
- a number has no source;
- the context and the code disagree (the code wins, but confirm);
- the environment is not sandbox;
- the estimated data volume is large: state it per case and confirm.

## 4. Write the test

In the test folder, following `CLAUDE.md` and the reference:
- `locustfile.py`: no host on the user class (the README says what to type in Host), token as a secret custom parameter, settings with correctly typed defaults, bounded
  work per user, timeouts, grouped failure reasons without URLs, `SETUP` failure for a missing token, `on_stop`
  cleanup, rows named by step, test data labelled with the agreed prefix.
- `README.md`: same sections as the reference README, filled from the context (cases, settings table, rows,
  failures table, Grafana, rehearsal, cleanup, report template).
- `_dryrun_test.py`, **only when the test writes data or sends large payloads** (see `CLAUDE.md`, "Check before
  anyone runs it"): a fake server for every host the test calls (same `--serve` pattern as the reference), and
  scenarios for: success, each failure type of each step, a hang (timeout), connection refused, missing token,
  the per-user limit, and Stop. For a read-only test, skip it and say so in the report; offer to add one if the
  user wants it.
- `results/.gitkeep`.

## 5. Check

Use the script version for the user's system: `.ps1` on Windows (PowerShell), `.sh` on macOS/Linux (bash).

1. If the test has a `_dryrun_test.py`: `.\tools\dryrun.ps1 -Test <name>` or `./tools/dryrun.sh <name>` (runs
   inside the Locust image with no network). Fix the test, not the checks, until all pass. If a check itself is
   wrong, say why before changing it.
2. Start the dashboard once (`.\run-local.ps1 -Test <name> -Detach -Port 18089`, or
   `TEST=<name> DETACH=1 PORT=18089 ./run-local.sh`), confirm every setting appears on the start form, then
   `docker stop rata-locust-local`. If Docker isn't running, ask the user to start it.
3. Never run the test against sandbox or any real host. The user rehearses locally with their own token.

## 6. Report

Tell the user:
- what the test does, per step, and which code it is based on;
- each case with its estimated load and data volume;
- assumptions made, and answers still missing;
- the dry-run result;
- that a person must review the script before it goes to the Locust VM, and what to look at first (data volume,
  hosts it calls, the per-user limit);
- next steps: local rehearsal (`.\run-local.ps1 -Test <name>` or `TEST=<name> ./run-local.sh`; 1 user, small
  values), then merge to `master`: the Locust VM picks it up by itself (`vm/README.md`).

Do not commit or push unless asked.

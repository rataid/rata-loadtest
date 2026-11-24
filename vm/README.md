# Locust VM setup (one time)

After this setup the Locust dashboard always has the latest tests from this repo's `master` branch. A new or
changed test appears in the dashboard a minute or two after it's merged. Nobody has to copy files or restart
Locust.

## How it works

| Container | Image | What it does |
|---|---|---|
| `git-sync` | `registry.k8s.io/git-sync/git-sync:v4.4.0` | pulls `master` every 60 s with a read-only deploy key |
| `locust` | `locustio/locust:2.47.0` | runs [`supervisor.py`](supervisor.py), which starts Locust with every test under `tests/` and `--class-picker` |

On a new commit the supervisor:
1. checks the new tests load (`locust --list`). If they don't, it keeps the current version running and logs the
   error;
2. waits until no test is running (0 users), so a live load test is never cut off;
3. restarts Locust on the new commit. The dashboard is down for a few seconds.

In the dashboard, each test is one entry in **User classes**: tick the one to run.

## Setup

On the VM, in a new folder (e.g. `~/rata-loadtest-vm`):

1. **Deploy key** (read-only access to this repo only):
   ```bash
   mkdir secrets
   ssh-keygen -t ed25519 -N "" -C "locust-vm" -f secrets/deploy_key
   ssh-keyscan github.com > secrets/known_hosts
   sudo chown 65533 secrets/deploy_key && chmod 400 secrets/deploy_key   # git-sync runs as user 65533
   cat secrets/deploy_key.pub
   ```
   A repo admin adds the printed public key under **GitHub → rataid/rata-loadtest → Settings → Deploy keys →
   Add deploy key**, with **Allow write access** left off.

2. **Compose file:** copy [`docker-compose.yml`](docker-compose.yml) into the folder, next to `secrets/`.
   - Dashboard login: put the settings you use today under `locust.environment`
     (`LOCUST_ARGS: "--web-login"` or `LOCUST_WEB_AUTH`, `LOCUST_*` variables are passed on).
   - Port: it publishes `8089`. Stop the current Locust container first, or change the port.
   - Locust version: `locustio/locust:2.47.0` is the version the tests are checked with. Tell the team before
     changing it.

3. **Start:**
   ```bash
   docker compose up -d
   docker compose logs -f
   ```
   Expect `updated successfully` from git-sync, then `[supervisor] starting Locust on <commit>` and
   `Starting web interface`. The dashboard should list `DesignExportUser` under **User classes**.

## Try it locally first

[`docker-compose.local.yml`](docker-compose.local.yml) runs the same setup on your machine, synced from your local
clone's committed `master` (no deploy key, nothing pushed), with the dashboard on http://127.0.0.1:8090:
```bash
docker compose -f vm/docker-compose.local.yml up -d
docker compose -f vm/docker-compose.local.yml down -v
```

## Later

| Situation | What to do |
|---|---|
| New or changed test merged to `master` | nothing |
| A merged test doesn't load | nothing on the VM: the old version keeps running; the log shows `don't load` with the error, and the team fixes the test |
| `vm/supervisor.py` changed | `docker compose restart locust` (the supervisor itself only reloads on restart) |
| Upgrade Locust | change the `locust` image tag, `docker compose up -d` |
| Stop it | `docker compose down` |

Don't put tokens in the compose file or the environment: values given at startup can be read in the dashboard
page source. Testers type their token into the start form for each run.

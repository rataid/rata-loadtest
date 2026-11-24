"""
Keep the Locust dashboard running with the latest tests from this repo (runs on the Locust VM).

git-sync (see vm/docker-compose.yml) keeps a checkout of `master` at REPO_DIR, switching a
symlink to each new commit. This script:

  1. starts Locust with every test under tests/ and --class-picker, so the dashboard lists
     each test's user class and you pick the one to run;
  2. checks for a new commit every CHECK_SECONDS;
  3. on a new commit, checks that the new tests load (locust --list); if they don't, it keeps
     the old version running and logs the error;
  4. restarts Locust on the new commit only when no test is running (0 users), so a live run
     is never cut off. The dashboard is down for a few seconds while it restarts.

Settings (environment):
  REPO_DIR        git-sync link to the checkout          default /git/rata-loadtest
  CHECK_SECONDS   how often to look for a new commit     default 30
  LOCUST_ARGS     extra Locust options, e.g. "--web-login"; LOCUST_* variables are passed on too
"""
import os
import shlex
import signal
import subprocess
import sys
import time

REPO_DIR = os.environ.get("REPO_DIR", "/git/rata-loadtest")
CHECK_SECONDS = int(os.environ.get("CHECK_SECONDS", "30"))
EXTRA_ARGS = shlex.split(os.environ.get("LOCUST_ARGS", ""))
STATE_FILE = os.environ.setdefault("LOCUST_STATE_FILE", "/tmp/locust-state")
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locust_state_hook.py")


def log(message):
    print(f"[supervisor] {message}", flush=True)


def current_checkout():
    """The commit folder the git-sync link points to, or None before the first sync."""
    path = os.path.realpath(REPO_DIR)
    return path if os.path.isdir(os.path.join(path, "tests")) else None


def locustfiles(checkout):
    return f"{os.path.join(checkout, 'tests')},{HOOK}"


def loads_ok(checkout):
    """Import the tests without starting anything. Returns (ok, output)."""
    result = subprocess.run(
        ["locust", "-f", locustfiles(checkout), "--list"],
        cwd=checkout, capture_output=True, text=True, timeout=120,
    )
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def start(checkout):
    try:
        os.remove(STATE_FILE)
    except FileNotFoundError:
        pass
    log(f"starting Locust on {os.path.basename(checkout)}")
    return subprocess.Popen(["locust", "-f", locustfiles(checkout), "--class-picker", *EXTRA_ARGS], cwd=checkout)


def stop(process):
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def test_running():
    """True while users are running or spawning. Unknown state counts as running (safe side)."""
    try:
        with open(STATE_FILE) as f:
            state, users = f.read().split()
    except (OSError, ValueError):
        return True
    if state in ("ready", "stopped"):
        return False
    return state == "spawning" or int(users) > 0


def main():
    process = None
    running_checkout = None
    rejected = None  # last checkout that failed to load, so it isn't retried every check
    waiting_for = None  # checkout already logged as waiting, so the message shows once

    def shutdown(*_args):
        if process is not None:
            stop(process)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    while True:
        checkout = current_checkout()

        if checkout is None:
            log(f"waiting for the first git-sync checkout at {REPO_DIR}")
        elif checkout not in (running_checkout, rejected):
            ok, output = loads_ok(checkout)
            if not ok:
                rejected = checkout
                log(f"new tests at {os.path.basename(checkout)} don't load, keeping the current version:\n{output}")
            elif process is None or process.poll() is not None:
                process, running_checkout = start(checkout), checkout
            elif test_running():
                if waiting_for != checkout:
                    waiting_for = checkout
                    log("new tests available; waiting for the running test to finish before restarting")
            else:
                log("new tests available; restarting Locust")
                stop(process)
                process, running_checkout = start(checkout), checkout
        elif process is not None and process.poll() is not None:
            log(f"Locust exited with code {process.returncode}; starting it again")
            process = start(running_checkout)

        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    main()

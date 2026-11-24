"""
Loaded next to the tests by vm/supervisor.py (not a test: it has no user class).

Every few seconds it writes the runner state and user count to a file, so the supervisor
can tell whether a load test is running before it restarts Locust with new tests.
It reads the state inside Locust, so it works even when the dashboard needs a login.
"""
import os

import gevent
from locust import events
from locust.runners import WorkerRunner

STATE_FILE = os.environ.get("LOCUST_STATE_FILE", "/tmp/locust-state")


@events.init.add_listener
def write_state(environment, **_kwargs):
    runner = environment.runner
    if runner is None or isinstance(runner, WorkerRunner):
        return

    def loop():
        while True:
            try:
                with open(STATE_FILE + ".tmp", "w") as f:
                    f.write(f"{runner.state} {runner.user_count}\n")
                os.replace(STATE_FILE + ".tmp", STATE_FILE)
            except OSError:
                pass
            gevent.sleep(5)

    gevent.spawn(loop)

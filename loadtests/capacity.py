"""100-school / 2,000 distinct-account browser polling model; local targets only.

Uses the actual visible-page intervals, a separate session for every actor, real
HTTP/RLS and the production proxy. This is a read workload: write/import/PDF,
login storms, parent journeys and failover require their separate test profiles.
"""

import itertools
import json
import os
import random
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from locust import HttpUser, between, events, task

DATA = json.loads(Path(os.environ["CAPACITY_DATA_FILE"]).read_text())
if DATA.get("synthetic") is not True or len(DATA["schools"]) < 100:
    raise RuntimeError("Capacity profile requires at least 100 synthetic schools")
_actors = itertools.count()
_started = set()
_schools = set()
_roles = Counter()


@events.test_stop.add_listener
def record_actors(environment, **kwargs):
    Path(os.environ["CAPACITY_DATA_FILE"]).with_name("actors.json").write_text(
        json.dumps({"distinct_actors": len(_started), "schools": len(_schools),
                    "roles": dict(_roles)}), encoding="utf-8"
    )


class CapacityUser(HttpUser):
    wait_time = between(0.5, 1.0)

    def on_start(self):
        if urlparse(self.host).hostname not in {"frontend", "localhost", "127.0.0.1"}:
            raise RuntimeError("Capacity profile may only target the isolated local stack")
        self.actor = next(_actors)
        school = DATA["schools"][self.actor % len(DATA["schools"])]
        slot = self.actor // len(DATA["schools"])
        roles = ("manager", "vice_principal", "counselor")
        if slot < 3:
            role = roles[slot]
            session = school["sessions"][role]
        else:
            role = "teacher"
            # Deliberately do not wrap: repeated accounts would hide real pressure.
            session = school["sessions"]["teachers"][slot - 3]
        self.client.cookies.set("sessionid", session, secure=False)
        self.school_id = school["id"]
        self.role = role
        self.ready = False
        self.next_bootstrap = 0.0
        jitter = random.uniform(0.85, 1.15)  # noqa: S311 - polling phase, not a secret
        if role == "teacher":
            paths = [
                ("/api/v1/attendance/current-period/", 15),
                ("/api/v1/teacher/follow-up-requests/", 30),
                ("/api/v1/referrals/mine/?status=OPEN&page=1", 30),
            ]
        elif role == "counselor":
            paths = [
                ("/api/v1/counselor/dashboard/", 30),
                ("/api/v1/counselor/cases/?status=live&page=1", 60),
            ]
        else:
            paths = [
                ("/api/v1/dashboard/today/", 15),
                ("/api/v1/dashboard/overview/", 120),
                ("/api/v1/dashboard/attention/", 60),
                ("/api/v1/reports/absence/?preset=LAST_30_DAYS&page_size=25", 60),
            ]
        self.polls = [[path, seconds * jitter, 0.0, 0] for path, seconds in paths]
        self.bootstrap()

    def bootstrap(self):
        # Keep failed actors alive and record the failure. Replacing them would
        # consume new credentials indefinitely and corrupt the concurrency model.
        with self.client.get(
            "/api/v1/auth/me/", name="initial/auth/me", timeout=15, catch_response=True
        ) as response:
            if response.status_code == 200:
                self.ready = (
                    (response.json().get("active_school") or {}).get("id") == self.school_id
                )
                if not self.ready:
                    response.failure("Synthetic actor did not enter its own school")
        # Only this isolated HTTP target needs Secure cookies relaxed; production
        # settings retain Secure and the application image is unchanged.
        for cookie in self.client.cookies:
            cookie.secure = False
        self.next_bootstrap = time.monotonic() + 30
        if self.ready:
            _started.add(self.actor)
            _schools.add(self.school_id)
            _roles[self.role] += 1
            if self.role == "teacher":
                self.client.get(
                    "/api/v1/attendance/sections/", name="initial/teacher/sections", timeout=15
                )

    @task
    def visible_page(self):
        now = time.monotonic()
        if not self.ready:
            if now >= self.next_bootstrap:
                self.bootstrap()
            return
        for poll in self.polls:
            path, interval, due, failures = poll
            if now >= due:
                response = self.client.get(path, name=path.split("?")[0], timeout=15)
                delay = interval
                if response.status_code in (0, 429) or response.status_code >= 500:
                    poll[3] = min(failures + 1, 5)
                    delay = max(
                        min(interval * 2 ** poll[3], 300),
                        float(response.headers.get("Retry-After", "0")),
                    )
                else:
                    poll[3] = 0
                poll[2] = time.monotonic() + delay

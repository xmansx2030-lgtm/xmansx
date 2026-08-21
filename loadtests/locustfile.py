"""Phase 19 HTTP load profiles for the isolated Xmansx stack."""

import itertools
import json
import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from locust import HttpUser, between, task

PROFILE = os.environ.get("PHASE19_PROFILE", "mixed")
PDF_OFFSET = int(os.environ.get("PHASE19_PDF_OFFSET", "0"))
DEFAULT_DATA_FILE = Path(__file__).resolve().parents[1] / "phase19-data.json"
DATA = json.loads(Path(os.environ.get("PHASE19_DATA_FILE", DEFAULT_DATA_FILE)).read_text())
PASSWORD = DATA["password"]
PRIMARY = DATA["schools"][0]
_counter = itertools.count()
_counter_lock = threading.Lock()


def _next_index():
    with _counter_lock:
        return next(_counter)


class Phase19User(HttpUser):
    wait_time = between(0.15, 0.8)

    def on_start(self):
        original_request = self.client.request

        def local_http_request(*args, **kwargs):
            self._relax_local_secure_cookies()
            response = original_request(*args, **kwargs)
            self._relax_local_secure_cookies()
            return response

        self.client.request = local_http_request
        self.index = _next_index()
        self.school = DATA["schools"][self.index % len(DATA["schools"])]
        self.mobile = self._mobile()
        self.teacher_completed = False
        self.logged_in = PROFILE != "login"
        if PROFILE == "login":
            self._login()
        elif PROFILE != "device_events" and not (
            PROFILE == "mixed" and self._mixed_kind() == "device"
        ):
            session_key, csrf_token = self._credentials()
            self.client.cookies.set("sessionid", session_key, secure=False)
            self.client.cookies.set("csrftoken", csrf_token, secure=False)

    def _mobile(self):
        if PROFILE in {"teacher", "login"} and self.school["teachers"]:
            return self.school["teachers"][self.index % len(self.school["teachers"])]
        if PROFILE == "mixed":
            kind = self._mixed_kind()
            if kind == "teacher" and self.school["teachers"]:
                return self.school["teachers"][self.index % len(self.school["teachers"])]
            if kind == "vice_principal":
                return self.school["vice_principal"]
            if kind == "counselor":
                return self.school["counselor"]
            return self.school["manager"]
        if PROFILE == "counselor":
            return self.school["counselor"]
        if PROFILE == "platform":
            return DATA["platform_admin"]
        if PROFILE == "pdf":
            return self.school["vice_principal"]
        return self.school["manager"]

    def _credentials(self):
        if PROFILE == "platform":
            return DATA["platform_admin_session"], DATA["platform_admin_csrf"]
        sessions = self.school["sessions"]
        csrf = self.school["csrf"]
        if PROFILE == "teacher":
            index = self.index % len(sessions["teachers"])
            return sessions["teachers"][index], csrf["teachers"][index]
        if PROFILE == "counselor":
            return sessions["counselor"], csrf["counselor"]
        if PROFILE == "pdf":
            index = self.index % len(self.school["pdf_sessions"])
            return self.school["pdf_sessions"][index], self.school["pdf_csrf"][index]
        if PROFILE == "mixed":
            kind = self._mixed_kind()
            if kind == "teacher":
                index = self.index % len(sessions["teachers"])
                return sessions["teachers"][index], csrf["teachers"][index]
            if kind == "vice_principal":
                return sessions["vice_principal"], csrf["vice_principal"]
            if kind == "counselor":
                return sessions["counselor"], csrf["counselor"]
        return sessions["manager"], csrf["manager"]

    def _mixed_kind(self):
        if self.index == 0:
            return "manager"
        if self.index == 1:
            return "vice_principal"
        if self.index == 2:
            return "counselor"
        if self.index % 10 == 3:
            return "device"
        return "teacher"

    def _relax_local_secure_cookies(self):
        for cookie in self.client.cookies:
            cookie.secure = False

    def _csrf_headers(self):
        return {"X-CSRFToken": self.client.cookies.get("csrftoken") or ""}

    def _login(self):
        csrf = self.client.get("/api/v1/auth/csrf/", name="auth/csrf")
        token = csrf.cookies.get("csrftoken") or self.client.cookies.get("csrftoken")
        # The isolated stack is HTTP-only while production cookies correctly carry Secure.
        self._relax_local_secure_cookies()
        with self.client.post(
            "/api/v1/auth/login/",
            json={"mobile": self.mobile, "password": PASSWORD},
            headers={"X-CSRFToken": token or ""},
            name="auth/login",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
                self.logged_in = True
                self._relax_local_secure_cookies()
            else:
                self.logged_in = False
                response.failure(f"login status {response.status_code}")

    @task
    def run_profile(self):
        profiles = {
            "login": self._login_burst,
            "teacher": self._teacher_attendance,
            "dashboard": self._dashboard,
            "student_profile": self._student_profile,
            "device_events": self._device_events,
            "counselor": self._counselor,
            "platform": self._platform,
            "pdf": self._pdf_generation,
            "mixed": self._mixed,
        }
        profiles[PROFILE]()

    def _login_burst(self):
        if self.logged_in:
            self.client.get("/api/v1/auth/me/", name="auth/me")

    def _teacher_attendance(self):
        self.client.get("/api/v1/attendance/current-period/", name="attendance/current-period")
        if self.teacher_completed:
            return
        self.client.get("/api/v1/attendance/sections/", name="attendance/sections")
        section_id = self.school["section_ids"][self.index % len(self.school["section_ids"])]
        with self.client.post(
            "/api/v1/attendance/sessions/start/",
            json={"section_id": section_id},
            headers=self._csrf_headers(),
            name="attendance/start",
            catch_response=True,
        ) as response:
            if response.status_code not in (200, 201):
                response.failure(f"start status {response.status_code}")
                return
            response.success()
            body = response.json()
        if body.get("status") == "IN_PROGRESS":
            with self.client.post(
                f"/api/v1/attendance/sessions/{body['id']}/submit/",
                json={"marks": []},
                headers=self._csrf_headers(),
                name="attendance/submit",
                catch_response=True,
            ) as submitted:
                if submitted.status_code in (200, 409):
                    submitted.success()
                else:
                    submitted.failure(f"submit status {submitted.status_code}")
        self.teacher_completed = True

    def _dashboard(self):
        self.client.get("/api/v1/dashboard/overview/", name="dashboard/overview")
        self.client.get("/api/v1/dashboard/today/", name="dashboard/today")
        self.client.get("/api/v1/attendance/monitoring/current/", name="attendance/monitoring")

    def _student_profile(self):
        if not self.school["student_ids"]:
            return
        student_id = self.school["student_ids"][self.index % len(self.school["student_ids"])]
        self.client.get(
            f"/api/v1/students/{student_id}/attendance-profile/?preset=ACADEMIC_YEAR",
            name="student/attendance-profile",
        )
        self.client.get(
            f"/api/v1/students/{student_id}/attendance-days/?page_size=25",
            name="student/attendance-days",
        )

    def _device_events(self):
        students = self.school["student_ids"]
        if not students:
            return
        stamp = datetime.now(UTC).isoformat()
        event_id = uuid.uuid4().hex
        event = {
            "device_id": self.school["device_id"],
            "external_user_id": f"student-{students[self.index % len(students)]}",
            "occurred_at": stamp,
            "event_type": "CHECK_IN",
            "dedupe_key": event_id,
        }
        with self.client.post(
            "/api/v1/bridge/events/batch/",
            json={"events": [event, event]},
            headers={"Authorization": f"Bearer {self.school['bridge_token']}"},
            name="bridge/events/batch",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"bridge batch status {response.status_code}")

    def _counselor(self):
        self.client.get("/api/v1/counselor/dashboard/", name="counselor/dashboard")
        self.client.get("/api/v1/counselor/cases/?page_size=25", name="counselor/cases")

    def _platform(self):
        self.client.get("/api/v1/platform/overview/", name="platform/overview")
        self.client.get("/api/v1/platform/schools/?page_size=25", name="platform/schools")

    def _pdf_generation(self):
        if self.teacher_completed:
            self.client.get(
                "/api/v1/health/live/",
                headers={"Connection": "close"},
                name="health/during-pdf",
            )
            return
        students = self.school["student_ids"]
        student_id = students[(PDF_OFFSET + self.index) % len(students)]
        target_date = datetime.now(UTC).date().isoformat()
        with self.client.post(
            "/api/v1/documents/generate/",
            json={
                "student_id": student_id,
                "document_type": "ATTENDANCE_COMMITMENT",
                "from_date": target_date,
                "to_date": target_date,
            },
            headers={**self._csrf_headers(), "Connection": "close"},
            name="documents/generate",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                response.success()
                self.teacher_completed = True
            elif response.status_code == 429 and response.json().get("code") == "PDF_GENERATION_BUSY":
                response.request_meta["name"] = "documents/generate-busy"
                response.success()
                self.teacher_completed = True
            else:
                response.failure(f"document status {response.status_code}")

    def _mixed(self):
        kind = self._mixed_kind()
        if kind == "teacher":
            self._teacher_attendance()
        elif kind in {"manager", "vice_principal"}:
            self._dashboard()
        elif kind == "counselor":
            self._counselor()
        else:
            self._device_events()

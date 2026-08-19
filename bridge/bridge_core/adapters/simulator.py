"""موصل محاكاة (تطوير/اختبار فقط) — يقرأ أحداثًا من ملف JSON محلي.

يحاكي جهازًا حقيقيًا لاختبار المسار كاملًا (جهاز ← جسر ← طابور ← SaaS) دون
عتاد — وليس backdoor إنتاجيًا: مجرد قارئ ملف داخل شبكة المشغل.
صيغة الملف: [{"external_event_id", "external_user_id", "occurred_at", ...}]
"""

import json
from pathlib import Path

from bridge_core.adapters.base import DeviceCapability


class SimulatorConnector:
    def __init__(self, config: dict):
        self.config = config
        self.events_file = config.get("events_file", "")

    def fetch_events(self, since: str | None) -> list[dict]:
        path = Path(self.events_file)
        if not self.events_file or not path.exists():
            return []
        events = json.loads(path.read_text(encoding="utf-8"))
        if since:
            events = [e for e in events if e.get("occurred_at", "") > since]
        return events

    def test_connection(self) -> dict:
        if self.events_file and Path(self.events_file).exists():
            return {"ok": True, "detail": "simulator ready"}
        return {"ok": False, "detail": "events file not found"}

    def capabilities(self) -> set[DeviceCapability]:
        return {
            DeviceCapability.READ_USERS,
            DeviceCapability.CREATE_USER,
            DeviceCapability.UPDATE_USER,
            DeviceCapability.DELETE_USER,
        }

    def _users_path(self) -> Path:
        return Path(self.config.get("users_file", ""))

    def read_users(self) -> list[dict]:
        path = self._users_path()
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_users(self, users: list[dict]) -> None:
        path = self._users_path()
        if not path:
            raise RuntimeError("simulator users_file is not configured")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(users, ensure_ascii=False), encoding="utf-8")

    def create_user(self, external_user_id: str, display_name: str) -> dict:
        users = self.read_users()
        if any(user.get("external_user_id") == external_user_id for user in users):
            return {"result": "SUCCEEDED", "already_exists": True}
        users.append(
            {"external_user_id": external_user_id, "display_name": display_name,
             "status": "ACTIVE"}
        )
        self._write_users(users)
        return {"result": "SUCCEEDED"}

    def update_user(self, external_user_id: str, display_name: str) -> dict:
        users = self.read_users()
        for user in users:
            if user.get("external_user_id") == external_user_id:
                user["display_name"] = display_name
                self._write_users(users)
                return {"result": "SUCCEEDED"}
        return self.create_user(external_user_id, display_name)

    def delete_user(self, external_user_id: str) -> dict:
        users = self.read_users()
        remaining = [user for user in users if user.get("external_user_id") != external_user_id]
        self._write_users(remaining)
        return {"result": "SUCCEEDED", "already_absent": len(remaining) == len(users)}

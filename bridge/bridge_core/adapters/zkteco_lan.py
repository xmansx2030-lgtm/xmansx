"""موصل LAN لأجهزة ZKTeco المستقلة، ومنها MB2000.

يستخدم بروتوكول ZK المستقل عبر TCP/UDP داخل شبكة المدرسة فقط. الاعتماد البرمجي
اختياري ومفصول عن قلب الجسر؛ لا تُقرأ أو تُرسل قوالب الوجه/البصمة مطلقًا.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from ipaddress import IPv4Address, ip_address
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bridge_core.adapters.base import DeviceCapability

logger = logging.getLogger("bridge.zkteco")


class ZKTecoConfigurationError(ValueError):
    """إعداد شبكة محلية أو Comm Key غير صالح."""


def _load_pyzk_factory():
    try:
        from zk import ZK  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "دعم ZKTeco غير مثبت على هذا الجسر. ثبّت متطلبات "
            "bridge/requirements-zkteco.txt ثم أعد تشغيل الخدمة."
        ) from exc
    return ZK


class ZKTecoLanConnector:
    """قراءة الحضور وإدارة دليل المستخدمين عبر منفذ ZKTeco المحلي (4370)."""

    def __init__(self, config: dict, *, client_factory: Callable | None = None):
        self.config = config
        self.ip = self._validate_ip(config.get("local_ip"))
        self.port = self._validate_port(config.get("local_port"))
        self.connection_type = str(config.get("connection_type") or "TCP").upper()
        if self.connection_type not in {"TCP", "UDP"}:
            raise ZKTecoConfigurationError("نوع اتصال ZKTeco يجب أن يكون TCP أو UDP.")
        self.comm_key = self._validate_comm_key(config.get("connection_secret"))
        try:
            self.timezone = ZoneInfo(str(config.get("timezone") or "Asia/Riyadh"))
        except ZoneInfoNotFoundError as exc:
            raise ZKTecoConfigurationError("المنطقة الزمنية المرسلة للجسر غير صالحة.") from exc
        self.timeout = self._validate_timeout(config.get("connection_timeout_seconds"))
        self._client_factory = client_factory

    @staticmethod
    def _validate_ip(raw_ip: object) -> str:
        value = str(raw_ip or "").strip()
        if not value:
            raise ZKTecoConfigurationError("عنوان IP المحلي لجهاز ZKTeco مطلوب.")
        try:
            parsed = ip_address(value)
        except ValueError as exc:
            raise ZKTecoConfigurationError("عنوان IP لجهاز ZKTeco غير صالح.") from exc
        if not isinstance(parsed, IPv4Address):
            raise ZKTecoConfigurationError("موصل ZKTeco الحالي يدعم IPv4 داخل LAN فقط.")
        if not parsed.is_private or parsed.is_loopback or parsed.is_multicast:
            raise ZKTecoConfigurationError(
                "يجب استخدام عنوان IPv4 خاص داخل شبكة المدرسة، وليس عنوانًا عامًا."
            )
        return str(parsed)

    @staticmethod
    def _validate_port(raw_port: object) -> int:
        try:
            port = int(raw_port or 4370)
        except (TypeError, ValueError) as exc:
            raise ZKTecoConfigurationError("منفذ ZKTeco غير صالح.") from exc
        if not 1 <= port <= 65535:
            raise ZKTecoConfigurationError("منفذ ZKTeco يجب أن يكون بين 1 و65535.")
        return port

    @staticmethod
    def _validate_comm_key(raw_key: object) -> int:
        value = str(raw_key or "0").strip()
        if not value.isdecimal():
            raise ZKTecoConfigurationError("Comm Key يجب أن يتكون من أرقام فقط.")
        key = int(value)
        if not 0 <= key <= 999999:
            raise ZKTecoConfigurationError("Comm Key يجب أن يكون من 0 إلى 999999.")
        return key

    @staticmethod
    def _validate_timeout(raw_timeout: object) -> int:
        try:
            timeout = int(raw_timeout or 10)
        except (TypeError, ValueError) as exc:
            raise ZKTecoConfigurationError("مهلة اتصال ZKTeco غير صالحة.") from exc
        if not 1 <= timeout <= 60:
            raise ZKTecoConfigurationError("مهلة الاتصال يجب أن تكون بين 1 و60 ثانية.")
        return timeout

    def _new_client(self):
        factory = self._client_factory or _load_pyzk_factory()
        return factory(
            self.ip,
            port=self.port,
            timeout=self.timeout,
            password=self.comm_key,
            force_udp=self.connection_type == "UDP",
            ommit_ping=True,
            encoding="UTF-8",
        )

    @contextmanager
    def _connection(self) -> Iterator[object]:
        connection = None
        try:
            connection = self._new_client().connect()
            yield connection
        finally:
            if connection is not None:
                try:
                    connection.disconnect()
                except Exception as exc:
                    logger.debug("ZKTeco disconnect failed: %s", exc)

    def _local_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=self.timezone)
        return value.astimezone(self.timezone)

    @staticmethod
    def _optional_call(connection: object, method: str) -> str:
        try:
            value = getattr(connection, method)()
        except Exception:
            return ""
        return str(value or "").strip()

    def test_connection(self) -> dict:
        try:
            with self._connection() as connection:
                device_time = connection.get_time()
                metadata = {
                    "firmware": self._optional_call(connection, "get_firmware_version"),
                    "serial_number": self._optional_call(connection, "get_serialnumber"),
                    "platform": self._optional_call(connection, "get_platform"),
                    "device_name": self._optional_call(connection, "get_device_name"),
                }
            return {
                "ok": True,
                "detail": "تم الاتصال بجهاز ZKTeco وقراءة ساعة الجهاز بنجاح.",
                "protocol": f"{self.connection_type}/{self.port}",
                "device_time": self._local_datetime(device_time).isoformat(),
                **{key: value for key, value in metadata.items() if value},
            }
        except Exception as exc:
            return {
                "ok": False,
                "detail": (
                    f"تعذر اتصال ZKTeco عبر {self.connection_type}/{self.port}: "
                    f"{str(exc)[:140]}"
                ),
                "protocol": f"{self.connection_type}/{self.port}",
            }

    def fetch_events(self, since: str | None) -> list[dict]:
        with self._connection() as connection:
            attendances = list(connection.get_attendance() or [])

        since_dt = None
        if since:
            since_dt = datetime.fromisoformat(str(since).replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=self.timezone)

        events = []
        for attendance in attendances:
            occurred_at = self._local_datetime(attendance.timestamp)
            if since_dt is not None and occurred_at <= since_dt.astimezone(self.timezone):
                continue
            external_user_id = str(attendance.user_id).strip()
            if not external_user_id:
                continue
            fingerprint = "|".join(
                (
                    external_user_id,
                    occurred_at.isoformat(),
                    str(getattr(attendance, "status", "")),
                    str(getattr(attendance, "punch", "")),
                )
            )
            events.append(
                {
                    "external_event_id": "zk-"
                    + hashlib.sha256(fingerprint.encode()).hexdigest()[:40],
                    "external_user_id": external_user_id,
                    "occurred_at": occurred_at.isoformat(),
                    # حقول status/punch تختلف حسب firmware ولا تثبت طريقة التحقق بأمان.
                    "verification_method": "UNKNOWN",
                    "event_type": "CHECK_IN",
                }
            )
        events.sort(key=lambda item: (item["occurred_at"], item["external_event_id"]))
        return events

    def capabilities(self) -> set[DeviceCapability]:
        return {
            DeviceCapability.READ_USERS,
            DeviceCapability.CREATE_USER,
            DeviceCapability.UPDATE_USER,
            DeviceCapability.DELETE_USER,
        }

    def read_users(self) -> list[dict]:
        with self._connection() as connection:
            users = list(connection.get_users() or [])
        return [
            {
                "external_user_id": str(user.user_id),
                "display_name": str(user.name or ""),
                "status": "ACTIVE",
            }
            for user in users
            if str(user.user_id).strip()
        ]

    def _find_user(self, connection: object, external_user_id: str):
        expected = str(external_user_id).strip()
        return next(
            (user for user in connection.get_users() if str(user.user_id) == expected),
            None,
        )

    def _validate_external_user_id(self, external_user_id: str) -> str:
        value = str(external_user_id).strip()
        if not value or len(value) > 9 or not value.isdecimal():
            raise ZKTecoConfigurationError("معرف مستخدم MB2000 يجب أن يكون رقمًا من 1 إلى 9 خانات.")
        return value

    def create_user(self, external_user_id: str, display_name: str) -> dict:
        user_id = self._validate_external_user_id(external_user_id)
        with self._connection() as connection:
            existing = self._find_user(connection, user_id)
            if existing is not None:
                return {"result": "SUCCEEDED", "already_exists": True}
            users = list(connection.get_users() or [])
            next_uid = max((int(user.uid) for user in users), default=0) + 1
            connection.set_user(
                uid=next_uid,
                name=str(display_name)[:24],
                privilege=0,
                password="",
                group_id="",
                user_id=user_id,
                card=0,
            )
        return {"result": "SUCCEEDED"}

    def update_user(self, external_user_id: str, display_name: str) -> dict:
        user_id = self._validate_external_user_id(external_user_id)
        with self._connection() as connection:
            existing = self._find_user(connection, user_id)
            if existing is None:
                return {"result": "FAILED_FINAL", "error_code": "DEVICE_USER_NOT_FOUND"}
            connection.set_user(
                uid=int(existing.uid),
                name=str(display_name)[:24],
                privilege=int(getattr(existing, "privilege", 0)),
                password=str(getattr(existing, "password", "")),
                group_id=str(getattr(existing, "group_id", "")),
                user_id=user_id,
                card=int(getattr(existing, "card", 0)),
            )
        return {"result": "SUCCEEDED"}

    def delete_user(self, external_user_id: str) -> dict:
        user_id = self._validate_external_user_id(external_user_id)
        with self._connection() as connection:
            existing = self._find_user(connection, user_id)
            if existing is None:
                return {"result": "SUCCEEDED", "already_absent": True}
            connection.delete_user(uid=int(existing.uid))
        return {"result": "SUCCEEDED"}

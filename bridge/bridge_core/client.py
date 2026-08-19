"""عميل SaaS — ‏HTTPS للخارج فقط، برمز اعتماد الجسر، مع Retry/Backoff منضبط.

- ‏5xx/انقطاع/مهلة: يعاد لاحقًا (backoff أسي بسقف) — الحدث يبقى في الطابور.
- ‏4xx (اعتماد/حمولة): لا إعادة عمياء — يرفع خطأ نهائيًا ليعالج (تدوير رمز/إصلاح).
- النقل قابل للحقن (transport) — اختبارات الوحدة بلا شبكة.
"""

import json
import time
import urllib.error
import urllib.request

MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_CAP_SECONDS = 60.0


class BridgeAuthError(Exception):
    """‏4xx — لا يعاد: الرمز مرفوض أو الحمولة فاسدة."""


class RetryableError(Exception):
    """شبكة/مهلة/5xx — الحدث يبقى في الطابور ويعاد لاحقًا."""


def _default_transport(url: str, payload: dict, token: str, timeout: float) -> dict:
    request = urllib.request.Request(  # noqa: S310 — عنوان SaaS من الإعداد الموثوق
        url,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        if 400 <= exc.code < 500:
            raise BridgeAuthError(f"HTTP {exc.code}") from exc
        raise RetryableError(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RetryableError(str(exc)) from exc


class SaaSClient:
    def __init__(self, *, base_url: str, credential: str, transport=None,
                 timeout: float = 15.0, sleep=time.sleep):
        self.base_url = base_url.rstrip("/")
        self.credential = credential
        self.transport = transport or _default_transport
        self.timeout = timeout
        self.sleep = sleep

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                return self.transport(url, payload, self.credential, self.timeout)
            except BridgeAuthError:
                raise  # لا إعادة على 4xx — قرار موثق
            except RetryableError as exc:
                last_error = exc
                delay = min(BACKOFF_BASE_SECONDS * (2**attempt), BACKOFF_CAP_SECONDS)
                self.sleep(delay)
        raise RetryableError(f"exhausted retries: {last_error}")

    def send_events(self, events: list[dict]) -> list[dict]:
        body = self._post("/api/v1/bridge/events/batch/", {"events": events})
        return body.get("results", [])

    def heartbeat(self, devices: list[dict]) -> list[dict]:
        """يرسل نبضة وتقارير الأجهزة — ويستلم إعدادات الأجهزة وطلبات الاختبار."""
        return self._post("/api/v1/bridge/heartbeat/", {"devices": devices}) or []

    def send_roster_read(
        self, *, job_id: int, device_id: int, users: list[dict], device_roster_version: str
    ) -> dict:
        return self._post(
            "/api/v1/bridge/roster/read/",
            {
                "job_id": job_id,
                "device_id": device_id,
                "users": users,
                "device_roster_version": device_roster_version,
            },
        )

    def send_roster_command_result(self, result: dict) -> dict:
        return self._post("/api/v1/bridge/roster/command-result/", result)

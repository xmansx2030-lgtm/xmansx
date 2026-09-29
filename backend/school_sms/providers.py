"""مزودان ثابتان؛ لا يقبل العميل عنوان URL ولا تُسجل بيانات الاعتماد أو الرسالة."""

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from school_sms.models import SmsProvider


class SmsProviderError(Exception):
    def __init__(self, code: str, *, ambiguous: bool = False):
        self.code = code
        self.ambiguous = ambiguous
        super().__init__(code)


@dataclass(frozen=True)
class SmsProviderResult:
    reference: str = ""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


_ALLOWED_URLS = frozenset({
    "https://www.dreams.sa/index.php/api/sendsms/",
    "https://www.msegat.com/gw/sendsms.php",
})


def _post(url: str, payload: dict[str, str], *, as_json: bool) -> str:
    if url not in _ALLOWED_URLS:
        raise SmsProviderError("SMS_ENDPOINT_UNSUPPORTED")
    body = (
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if as_json else urlencode(payload).encode("utf-8")
    )
    request = Request(  # noqa: S310 - fixed HTTPS allowlist above
        url,
        data=body,
        headers={
            "Content-Type": "application/json" if as_json else "application/x-www-form-urlencoded",
            "Accept": "application/json, text/plain",
        },
        method="POST",
    )
    try:
        with build_opener(_RejectRedirects).open(request, timeout=12) as response:
            return response.read(2048).decode("utf-8", errors="replace").strip()
    except HTTPError as exc:
        # A gateway can return 5xx after accepting the SMS; don't allow a blind retry.
        raise SmsProviderError(f"HTTP_{exc.code}", ambiguous=exc.code >= 500) from None
    except (URLError, TimeoutError, OSError) as exc:
        # بعد انقطاع الشبكة قد يكون المزود استلم الطلب؛ لا نعيد الإرسال آليًا.
        raise SmsProviderError("TRANSPORT_UNCERTAIN", ambiguous=True) from exc


def send_sms(*, provider: str, username: str, secret: str, sender: str,
             mobile: str, message: str) -> SmsProviderResult:
    number = mobile.removeprefix("+")
    if provider == SmsProvider.DREAMS:
        response = _post(
            "https://www.dreams.sa/index.php/api/sendsms/",
            {"user": username, "secret_key": secret, "to": number,
             "message": message, "sender": sender},
            as_json=False,
        )
        if re.fullmatch(r"-\d+", response):
            raise SmsProviderError(f"DREAMS_{response.removeprefix('-')}")
        match = re.fullmatch(r"Result\s*:\s*(\d+)(?::[^\s]*)?", response, re.I)
        if match:
            return SmsProviderResult(reference=match.group(1))
        if response == "1":
            return SmsProviderResult()
        raise SmsProviderError("DREAMS_RESPONSE_UNKNOWN", ambiguous=True)

    if provider == SmsProvider.MSEGAT:
        response = _post(
            "https://www.msegat.com/gw/sendsms.php",
            {"userName": username, "apiKey": secret, "numbers": number,
             "userSender": sender, "msg": message, "msgEncoding": "UTF8"},
            as_json=True,
        )
        try:
            result = json.loads(response)
        except ValueError as exc:
            raise SmsProviderError("MSEGAT_RESPONSE_UNKNOWN", ambiguous=True) from exc
        code = str(result.get("code", "")) if isinstance(result, dict) else str(result)
        if code in {"1", "M0000"}:
            reference = (
                result.get("id", result.get("reqBulkId", ""))
                if isinstance(result, dict) else ""
            )
            return SmsProviderResult(reference=str(reference)[:100])
        if re.fullmatch(r"[A-Z0-9]{1,12}", code):
            raise SmsProviderError(f"MSEGAT_{code}")
        raise SmsProviderError("MSEGAT_RESPONSE_UNKNOWN", ambiguous=True)

    raise SmsProviderError("SMS_PROVIDER_UNSUPPORTED")

"""تجهيز الجسر ومصادقته — هوية المدرسة من الرمز حصرًا، لا school_id من payload.

الرمز: ‏`brg_<identifier>_<secret>` — السر عالي الإنتروبيا يخزن SHA-256 فقط (لا KDF
بطيء: يتحقق مع كل دفعة/نبضة)، ويظهر كاملًا **مرة واحدة** عند الإنشاء/التدوير.
"""

import hashlib
import hmac
import secrets

from django.utils import timezone as dj_timezone

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from devices.models import BridgeStatus, DeviceBridgeInstallation


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _issue_token(installation: DeviceBridgeInstallation) -> str:
    secret = secrets.token_urlsafe(32)
    installation.credential_hash = _hash(secret)
    return f"brg_{installation.installation_identifier}_{secret}"


def create_bridge(*, school, name: str, actor, request=None):
    """ينشئ تثبيت جسر ويعيد (installation, token) — الرمز لا يخزن ولا يعرض ثانية."""
    installation = DeviceBridgeInstallation(
        school=school,
        installation_name=name.strip(),
        installation_identifier=secrets.token_hex(8),
        credential_hash="",
    )
    token = _issue_token(installation)
    installation.save()
    record_event(
        AuditAction.BRIDGE_CREATED,
        request=request,
        actor=actor,
        school=school,
        target_type="DeviceBridgeInstallation",
        target_id=installation.id,
        metadata={"name": installation.installation_name},  # لا secret أبدًا
    )
    return installation, token


def rotate_bridge_credential(*, installation, actor, request=None) -> str:
    """رمز جديد فورًا — القديم يبطل بلا فترة سماح."""
    token = _issue_token(installation)
    installation.save(update_fields=["credential_hash", "updated_at"])
    record_event(
        AuditAction.BRIDGE_CREDENTIAL_ROTATED,
        request=request,
        actor=actor,
        school=installation.school,
        target_type="DeviceBridgeInstallation",
        target_id=installation.id,
    )
    return token


def authenticate_bridge(token: str | None) -> DeviceBridgeInstallation:
    """يعيد التثبيت الموثق أو يرفض — مقارنة ثابتة الزمن، وتحديث آخر ظهور."""
    if not token or not token.startswith("brg_"):
        raise ApiError(
            "BRIDGE_AUTHENTICATION_REQUIRED",
            "رمز اعتماد الجسر مطلوب.",
            status_code=401,
        )
    parts = token.split("_", 2)
    if len(parts) != 3:
        raise ApiError("BRIDGE_AUTHENTICATION_FAILED", "رمز الجسر غير صالح.", status_code=403)
    _, identifier, secret = parts
    installation = (
        DeviceBridgeInstallation.objects.filter(installation_identifier=identifier)
        .select_related("school")
        .first()
    )
    if installation is None or not hmac.compare_digest(
        installation.credential_hash, _hash(secret)
    ):
        raise ApiError("BRIDGE_AUTHENTICATION_FAILED", "رمز الجسر غير صالح.", status_code=403)
    if installation.status != BridgeStatus.ACTIVE:
        raise ApiError("BRIDGE_DISABLED", "هذا الجسر موقوف.", status_code=403)
    installation.last_seen_at = dj_timezone.now()
    installation.save(update_fields=["last_seen_at", "updated_at"])
    return installation

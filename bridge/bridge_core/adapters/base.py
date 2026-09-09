"""عقد Adapter موحد — كل مصنّع يضيف كلاسًا يلتزم به.

صدق تقني إلزامي: دعم ZKTeco LAN منفذ ومختبر بمحاكاة البروتوكول، ويبقى اعتماد
الموديل/firmware الفعلي مشروطًا باختبار قبول على الجهاز نفسه.
"""

from enum import StrEnum
from typing import Protocol


class DeviceCapability(StrEnum):
    READ_USERS = "READ_USERS"
    CREATE_USER = "CREATE_USER"
    UPDATE_USER = "UPDATE_USER"
    DELETE_USER = "DELETE_USER"


class DeviceConnector(Protocol):
    """يتصل بجهاز واحد داخل LAN — لا يلمس الشبكة الخارجية إطلاقًا."""

    def fetch_events(self, since: str | None) -> list[dict]:
        """أحداث إثبات الحضور الجديدة — الحقول:
        external_event_id?, external_user_id, occurred_at (ISO بمنطقة زمنية),
        verification_method, event_type. **لا قوالب بيومترية أبدًا.**"""
        ...

    def test_connection(self) -> dict:
        """‏{"ok": bool, "detail": str} — بيانات وصفية آمنة فقط."""
        ...

    def capabilities(self) -> set[DeviceCapability]:
        ...

    def read_users(self) -> list[dict]:
        ...

    def create_user(self, external_user_id: str, display_name: str) -> dict:
        ...

    def update_user(self, external_user_id: str, display_name: str) -> dict:
        ...

    def delete_user(self, external_user_id: str) -> dict:
        ...


def build_connector(config: dict) -> DeviceConnector:
    """مصنع الموصلات حسب vendor — غير المنفذ يرفض بوضوح (لا ادعاء دعم)."""
    from bridge_core.adapters.simulator import SimulatorConnector
    from bridge_core.adapters.zkteco_lan import ZKTecoLanConnector

    vendor = (config.get("vendor") or "SIMULATOR").upper()
    if vendor in ("SIMULATOR", "GENERIC"):
        return SimulatorConnector(config)
    if vendor in ("ZKTECO", "ZK", "ZKTECO_MB2000", "MB2000"):
        return ZKTecoLanConnector(config)
    raise NotImplementedError(
        f"Adapter '{vendor}' غير منفذ بعد — يتطلب تكاملًا مختبرًا على الجهاز الفعلي."
    )

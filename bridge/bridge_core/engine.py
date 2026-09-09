"""محرك الجسر: دورة (نبضة → قراءة الأجهزة → طابور → إرسال دفعات) — headless.

مستقل عن غلاف Windows Service — يختبر وحده ويغلف لاحقًا (NSSM/sc). الأحداث تمر
بالطابور الدائم دائمًا: انقطاع SaaS يبقيها PENDING/FAILED_RETRYABLE وتفرغ عند
العودة **مرة واحدة بالضبط** (dedupe محلي + خادمي).
"""

import hashlib
import json
import logging

from bridge_core.adapters.base import DeviceCapability, build_connector
from bridge_core.client import BridgeAuthError, RetryableError, SaaSClient
from bridge_core.queue import DurableQueue

logger = logging.getLogger("bridge")


def roster_hash(users: list[dict]) -> str:
    canonical = [
        {
            "external_user_id": str(user.get("external_user_id", "")),
            "display_name": user.get("display_name", ""),
        }
        for user in users
    ]
    canonical.sort(key=lambda user: user["external_user_id"])
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class BridgeEngine:
    def __init__(
        self,
        *,
        client: SaaSClient,
        queue: DurableQueue,
        batch_size: int = 200,
        simulator_users_file: str = "",
    ):
        self.client = client
        self.queue = queue
        self.batch_size = batch_size
        self.simulator_users_file = simulator_users_file

    def poll_devices(
        self, device_configs: list[dict], device_reports: list[dict] | None = None
    ) -> int:
        """يقرأ أحداث كل جهاز عبر Adapter المناسب ويضيفها للطابور المحلي."""
        added = 0
        reports_by_device = {report["device_id"]: report for report in (device_reports or [])}
        for config in device_configs:
            report = reports_by_device.get(config.get("id"))
            try:
                connector = build_connector(config)
                events = connector.fetch_events(config.get("since"))
            except NotImplementedError as exc:
                logger.warning("adapter unavailable: %s", exc)
                if report is not None:
                    report["reachable"] = False
                    report["error_code"] = "ADAPTER_UNAVAILABLE"
                continue
            except Exception as exc:  # جهاز متعطل لا يوقف البقية
                logger.warning("device %s unreachable: %s", config.get("id"), exc)
                if report is not None:
                    report["reachable"] = False
                    report["error_code"] = "DEVICE_UNREACHABLE"
                continue
            if report is not None:
                report["reachable"] = True
                report.pop("error_code", None)
            for event in events:
                event.setdefault("device_id", config.get("id"))
                if self.queue.enqueue(event):
                    added += 1
        return added

    def flush(self) -> dict:
        """يرسل الدفعات المتراكمة — يعيد عدّادات النتائج."""
        totals = {"sent": 0, "duplicate": 0, "invalid": 0, "unmatched": 0, "retry": 0}
        while True:
            batch = self.queue.next_batch(self.batch_size)
            if not batch:
                break
            ids = [row[0] for row in batch]
            events = [row[1] for row in batch]
            try:
                results = self.client.send_events(events)
            except RetryableError:
                self.queue.mark(ids, "FAILED_RETRYABLE")
                totals["retry"] += len(ids)
                break  # الشبكة مقطوعة — نحاول في الدورة التالية
            except BridgeAuthError:
                # اعتماد مرفوض: لا إعادة عمياء — يترك PENDING وينبه المشغل
                logger.error("bridge credential rejected — rotate/fix configuration")
                totals["retry"] += len(ids)
                break
            self.queue.mark(ids, "ACKNOWLEDGED")
            for result in results:
                key = result.get("result", "invalid")
                totals[key if key in totals else "invalid"] += 1
                if key == "accepted":
                    totals["sent"] += 1
        return totals

    def heartbeat(self, device_reports: list[dict]) -> list[dict]:
        """نبضة دورية — تعيد إعدادات الأجهزة وطلبات اختبار الاتصال المعلقة."""
        try:
            return self.client.heartbeat(device_reports)
        except (RetryableError, BridgeAuthError) as exc:
            logger.warning("heartbeat failed: %s", exc)
            return []

    def run_once(self) -> dict:
        """دورة كاملة: نبضة (تجلب الأجهزة) → اختبارات اتصال → قراءة → إرسال."""
        configs = self.heartbeat([])
        reports = []
        roster_reads = 0
        roster_commands = 0
        for config in configs:
            if self.simulator_users_file and config.get("vendor", "").upper() == "SIMULATOR":
                config.setdefault("users_file", self.simulator_users_file)
            report = {"device_id": config["id"], "reachable": False}
            if config.get("test_requested"):
                try:
                    report["test_result"] = build_connector(config).test_connection()
                except Exception as exc:
                    report["test_result"] = {"ok": False, "detail": str(exc)[:200]}
            reports.append(report)
            if config.get("roster_read_job_id"):
                try:
                    connector = build_connector(config)
                    users = connector.read_users()
                    self.client.send_roster_read(
                        job_id=config["roster_read_job_id"],
                        device_id=config["id"],
                        users=users,
                        device_roster_version=roster_hash(users),
                    )
                    roster_reads += 1
                except Exception as exc:
                    logger.warning("roster read failed for device %s: %s", config.get("id"), exc)
            for command in config.get("roster_commands", []):
                try:
                    connector = build_connector(config)
                    action = command["action"]
                    capability = DeviceCapability(f"{action}_USER")
                    if capability not in connector.capabilities():
                        self.client.send_roster_command_result(
                            {
                                "job_id": command["job_id"],
                                "item_id": command["item_id"],
                                "command_id": command["command_id"],
                                "result": "FAILED_FINAL",
                                "error_code": "DEVICE_ROSTER_WRITE_UNSUPPORTED",
                            }
                        )
                        roster_commands += 1
                        continue
                    if action == "CREATE":
                        result = connector.create_user(
                            command["external_user_id"], command["display_name"]
                        )
                    elif action == "UPDATE":
                        result = connector.update_user(
                            command["external_user_id"], command["display_name"]
                        )
                    elif action == "DELETE":
                        result = connector.delete_user(command["external_user_id"])
                    else:
                        continue
                    self.client.send_roster_command_result(
                        {
                            "job_id": command["job_id"],
                            "item_id": command["item_id"],
                            "command_id": command["command_id"],
                            "result": result.get("result", "FAILED_FINAL"),
                            "error_code": result.get("error_code", ""),
                        }
                    )
                    roster_commands += 1
                except Exception as exc:
                    logger.warning(
                        "roster command failed for item %s: %s", command.get("item_id"), exc
                    )
                    try:
                        self.client.send_roster_command_result(
                            {
                                "job_id": command["job_id"],
                                "item_id": command["item_id"],
                                "command_id": command["command_id"],
                                "result": "FAILED_RETRYABLE",
                                "error_code": "DEVICE_COMMAND_EXECUTION_FAILED",
                            }
                        )
                        roster_commands += 1
                    except Exception as result_error:
                        logger.warning(
                            "roster command failure result failed for item %s: %s",
                            command.get("item_id"),
                            result_error,
                        )
        added = self.poll_devices(configs, reports)
        flushed = self.flush()
        if reports:
            self.heartbeat(reports)
        return {
            "devices": len(configs),
            "queued": added,
            "roster_reads": roster_reads,
            "roster_commands": roster_commands,
            **flushed,
        }

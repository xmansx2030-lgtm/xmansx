"""اختبارات محرك الجسر — الطابور الدائم، الإعادة، الدفعات، الاعتماد (بلا شبكة)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge_core.client import (  # noqa: E402
    BridgeAuthError,
    RetryableError,
    SaaSClient,
)
from bridge_core.engine import BridgeEngine  # noqa: E402
from bridge_core.queue import DurableQueue  # noqa: E402


def make_event(n: int, device_id: int = 1) -> dict:
    return {
        "device_id": device_id,
        "external_event_id": f"ev-{n}",
        "external_user_id": "1001",
        "occurred_at": f"2026-08-19T07:{n:02d}:00+03:00",
        "verification_method": "FINGERPRINT",
        "event_type": "CHECK_IN",
    }


class FakeTransport:
    """محاكاة SaaS — يبرمج بالردود: قوائم نتائج أو استثناءات."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    def __call__(self, url, payload, token, timeout):
        self.calls.append({"url": url, "payload": payload, "token": token})
        action = self.script.pop(0) if self.script else {"results": []}
        if isinstance(action, Exception):
            raise action
        if url.endswith("/heartbeat/"):
            return action
        return action


def make_client(script, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    return SaaSClient(
        base_url="https://saas.example",
        credential="brg_test_secret",
        transport=FakeTransport(script),
        sleep=sleeps.append,
    )


# ---------- الطابور الدائم ----------


def test_queue_survives_restart_and_dedupes(tmp_path):
    path = tmp_path / "q.sqlite3"
    queue = DurableQueue(path)
    assert queue.enqueue(make_event(1)) is True
    assert queue.enqueue(make_event(1)) is False  # تكرار محلي يتجاهل
    assert queue.enqueue(make_event(2)) is True
    queue.close()

    reopened = DurableQueue(path)  # إعادة تشغيل — الأحداث باقية (durable)
    batch = reopened.next_batch(10)
    assert [e["external_event_id"] for _, e in batch] == ["ev-1", "ev-2"]
    reopened.mark([batch[0][0]], "ACKNOWLEDGED")
    assert [e["external_event_id"] for _, e in reopened.next_batch(10)] == ["ev-2"]
    assert reopened.counts() == {"ACKNOWLEDGED": 1, "PENDING": 1}


def test_queue_no_biometric_fields_needed(tmp_path):
    """الطابور يحفظ الحد الأدنى فقط — الحمولة كما هي بلا أي حقول بيومترية."""
    queue = DurableQueue(tmp_path / "q.sqlite3")
    queue.enqueue(make_event(1))
    _, payload = queue.next_batch(1)[0]
    assert set(payload) == {
        "device_id",
        "external_event_id",
        "external_user_id",
        "occurred_at",
        "verification_method",
        "event_type",
    }


# ---------- العميل: retry/backoff و4xx ----------


def test_client_retries_on_5xx_with_backoff_then_succeeds():
    sleeps: list[float] = []
    client = make_client(
        [
            RetryableError("HTTP 500"),
            RetryableError("timeout"),
            {"results": [{"result": "accepted"}]},
        ],
        sleeps,
    )
    results = client.send_events([make_event(1)])
    assert results == [{"result": "accepted"}]
    assert sleeps == [1.0, 2.0]  # backoff أسي


def test_client_gives_up_after_max_attempts():
    client = make_client([RetryableError("down")] * 10, [])
    with pytest.raises(RetryableError):
        client.send_events([make_event(1)])


def test_client_does_not_retry_4xx():
    sleeps: list[float] = []
    client = make_client([BridgeAuthError("HTTP 403")], sleeps)
    with pytest.raises(BridgeAuthError):
        client.send_events([make_event(1)])
    assert sleeps == []  # لا إعادة عمياء على رفض الاعتماد


# ---------- المحرك: offline → online مرة واحدة بالضبط ----------


def test_offline_then_online_delivers_exactly_once(tmp_path):
    queue = DurableQueue(tmp_path / "q.sqlite3")
    for n in range(3):
        queue.enqueue(make_event(n))

    # ‏SaaS مقطوع: كل المحاولات تفشل → الأحداث تبقى قابلة للإعادة
    offline = BridgeEngine(client=make_client([RetryableError("down")] * 10, []), queue=queue)
    result = offline.flush()
    assert result["retry"] == 3
    assert queue.counts() == {"FAILED_RETRYABLE": 3}

    # عاد الاتصال: تفرغ مرة واحدة — والخادم يجيب duplicate لو أعيد إرسال قديم
    online = BridgeEngine(
        client=make_client(
            [{"results": [{"result": "accepted"}, {"result": "accepted"}, {"result": "duplicate"}]}]
        ),
        queue=queue,
    )
    result = online.flush()
    assert result["sent"] == 2 and result["duplicate"] == 1
    assert queue.counts() == {"ACKNOWLEDGED": 3}
    # لا شيء يرسل ثانية
    assert online.flush() == {"sent": 0, "duplicate": 0, "invalid": 0, "unmatched": 0, "retry": 0}


def test_ack_loss_replay_is_acknowledged_as_duplicate(tmp_path):
    queue = DurableQueue(tmp_path / "q.sqlite3")
    queue.enqueue(make_event(1))

    # The server may commit before the response is lost. The local row must remain replayable.
    offline = BridgeEngine(
        client=make_client([RetryableError("response lost after commit")] * 10, []),
        queue=queue,
    )
    assert offline.flush()["retry"] == 1
    assert queue.counts() == {"FAILED_RETRYABLE": 1}

    replay = BridgeEngine(
        client=make_client([{"results": [{"result": "duplicate"}]}]),
        queue=queue,
    )
    assert replay.flush()["duplicate"] == 1
    assert queue.counts() == {"ACKNOWLEDGED": 1}


def test_large_queue_survives_restart_and_drains_in_batches(tmp_path):
    path = tmp_path / "large.sqlite3"
    queue = DurableQueue(path)
    for n in range(5000):
        assert queue.enqueue(make_event(n)) is True
    queue.close()

    reopened = DurableQueue(path)
    batch_size = 500
    client = make_client([{"results": [{"result": "accepted"}] * batch_size} for _ in range(10)])
    result = BridgeEngine(client=client, queue=reopened, batch_size=batch_size).flush()

    assert result["sent"] == 5000
    assert len(client.transport.calls) == 10
    assert reopened.counts() == {"ACKNOWLEDGED": 5000}


def test_flush_batches_by_size(tmp_path):
    queue = DurableQueue(tmp_path / "q.sqlite3")
    for n in range(5):
        queue.enqueue(make_event(n))
    transport_script = [
        {"results": [{"result": "accepted"}] * 2},
        {"results": [{"result": "accepted"}] * 2},
        {"results": [{"result": "accepted"}]},
    ]
    client = make_client(transport_script)
    engine = BridgeEngine(client=client, queue=queue, batch_size=2)
    result = engine.flush()
    assert result["sent"] == 5
    assert len(client.transport.calls) == 3  # ‏5 أحداث ÷ دفعة 2 = 3 طلبات


def test_run_once_polls_simulator_and_reports_tests(tmp_path):
    events_file = tmp_path / "events.json"
    events_file.write_text(
        '[{"external_event_id": "s1", "external_user_id": "1001", '
        '"occurred_at": "2026-08-19T07:10:00+03:00", '
        '"verification_method": "FINGERPRINT", "event_type": "CHECK_IN"}]',
        encoding="utf-8",
    )
    device_config = {
        "id": 7,
        "name": "بوابة",
        "vendor": "SIMULATOR",
        "connection_type": "TCP",
        "local_ip": "",
        "local_port": None,
        "connection_secret": "",
        "test_requested": True,
        "events_file": str(events_file),
    }
    client = make_client(
        [
            [device_config],  # heartbeat الأولى تعيد الأجهزة
            {"results": [{"result": "accepted"}]},  # إرسال الدفعة
            [device_config],  # heartbeat التقارير
        ]
    )
    engine = BridgeEngine(client=client, queue=DurableQueue(tmp_path / "q.sqlite3"))
    result = engine.run_once()
    assert result["devices"] == 1 and result["queued"] == 1 and result["sent"] == 1
    # تقرير اختبار الاتصال أرسل في النبضة الثانية
    final_heartbeat = client.transport.calls[-1]["payload"]["devices"][0]
    assert final_heartbeat["test_result"]["ok"] is True


def test_run_once_reports_device_unreachable_when_poll_fails(tmp_path):
    device_config = {
        "id": 8,
        "name": "جهاز غير مدعوم",
        "vendor": "UNKNOWN_VENDOR",
        "connection_type": "TCP",
        "local_ip": "192.168.1.60",
        "local_port": 4370,
        "connection_secret": "",
        "test_requested": False,
    }
    client = make_client([[device_config], [device_config]])
    engine = BridgeEngine(client=client, queue=DurableQueue(tmp_path / "q.sqlite3"))

    result = engine.run_once()

    assert result["devices"] == 1 and result["queued"] == 0
    final_report = client.transport.calls[-1]["payload"]["devices"][0]
    assert final_report["reachable"] is False

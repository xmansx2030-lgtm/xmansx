from datetime import datetime
from types import SimpleNamespace

import pytest
from bridge_core.adapters.base import build_connector
from bridge_core.adapters.zkteco_lan import (
    ZKTecoConfigurationError,
    ZKTecoLanConnector,
)


class FakeConnection:
    def __init__(self):
        self.disconnected = False
        self.users = [
            SimpleNamespace(
                uid=1,
                user_id="1001",
                name="محمد",
                privilege=0,
                password="",
                group_id="",
                card=0,
            )
        ]
        self.attendances = [
            SimpleNamespace(
                user_id="1001",
                timestamp=datetime(2026, 9, 9, 7, 5),
                status=1,
                punch=0,
            ),
            SimpleNamespace(
                user_id="1002",
                timestamp=datetime(2026, 9, 9, 7, 10),
                status=1,
                punch=0,
            ),
        ]

    def disconnect(self):
        self.disconnected = True

    def get_time(self):
        return datetime(2026, 9, 9, 7, 11)

    def get_firmware_version(self):
        return "Ver 6.60"

    def get_serialnumber(self):
        return "MB2K-001"

    def get_platform(self):
        return "ZMM220_TFT"

    def get_device_name(self):
        return "MB2000"

    def get_attendance(self):
        return self.attendances

    def get_users(self):
        return self.users

    def set_user(self, **payload):
        existing = next(
            (user for user in self.users if str(user.user_id) == str(payload["user_id"])),
            None,
        )
        row = SimpleNamespace(**payload)
        if existing is None:
            self.users.append(row)
        else:
            self.users[self.users.index(existing)] = row

    def delete_user(self, *, uid):
        self.users = [user for user in self.users if int(user.uid) != int(uid)]


class FakeFactory:
    def __init__(self, connection=None, error=None):
        self.connection = connection or FakeConnection()
        self.error = error
        self.calls = []

    def __call__(self, ip, **kwargs):
        self.calls.append({"ip": ip, **kwargs})
        factory = self

        class Client:
            def connect(self):
                if factory.error:
                    raise factory.error
                return factory.connection

        return Client()


def config(**overrides):
    return {
        "vendor": "ZKTECO",
        "model": "MB2000",
        "local_ip": "192.168.10.25",
        "local_port": 4370,
        "connection_type": "TCP",
        "connection_secret": "123456",
        "timezone": "Asia/Riyadh",
        **overrides,
    }


def test_factory_selects_zkteco_mb2000_connector():
    assert isinstance(build_connector(config()), ZKTecoLanConnector)


def test_connection_uses_lan_port_comm_key_and_reads_device_metadata():
    factory = FakeFactory()
    connector = ZKTecoLanConnector(config(), client_factory=factory)

    result = connector.test_connection()

    assert result == {
        "ok": True,
        "detail": "تم الاتصال بجهاز ZKTeco وقراءة ساعة الجهاز بنجاح.",
        "protocol": "TCP/4370",
        "device_time": "2026-09-09T07:11:00+03:00",
        "firmware": "Ver 6.60",
        "serial_number": "MB2K-001",
        "platform": "ZMM220_TFT",
        "device_name": "MB2000",
    }
    assert factory.calls == [
        {
            "ip": "192.168.10.25",
            "port": 4370,
            "timeout": 10,
            "password": 123456,
            "force_udp": False,
            "ommit_ping": True,
            "encoding": "UTF-8",
        }
    ]
    assert factory.connection.disconnected is True


def test_connection_failure_is_actionable_and_does_not_raise():
    connector = ZKTecoLanConnector(
        config(connection_type="UDP"), client_factory=FakeFactory(error=OSError("timed out"))
    )
    result = connector.test_connection()
    assert result["ok"] is False
    assert result["protocol"] == "UDP/4370"
    assert "timed out" in result["detail"]


def test_fetch_events_normalizes_school_timezone_filters_and_dedupes_stably():
    factory = FakeFactory()
    connector = ZKTecoLanConnector(config(), client_factory=factory)

    events = connector.fetch_events("2026-09-09T07:05:00+03:00")

    assert len(events) == 1
    assert events[0]["external_user_id"] == "1002"
    assert events[0]["occurred_at"] == "2026-09-09T07:10:00+03:00"
    assert events[0]["verification_method"] == "UNKNOWN"
    assert events[0]["event_type"] == "CHECK_IN"
    assert events[0]["external_event_id"].startswith("zk-")
    assert connector.fetch_events(None)[1]["external_event_id"] == events[0]["external_event_id"]


def test_roster_crud_never_reads_or_writes_biometric_templates():
    factory = FakeFactory()
    connector = ZKTecoLanConnector(config(), client_factory=factory)

    assert connector.read_users()[0] == {
        "external_user_id": "1001",
        "display_name": "محمد",
        "status": "ACTIVE",
    }
    assert connector.create_user("1002", "أحمد")["result"] == "SUCCEEDED"
    assert connector.update_user("1002", "أحمد محمد")["result"] == "SUCCEEDED"
    assert (
        next(user for user in factory.connection.users if user.user_id == "1002").name
        == "أحمد محمد"
    )
    assert connector.delete_user("1002")["result"] == "SUCCEEDED"
    assert connector.delete_user("1002")["already_absent"] is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"local_ip": "8.8.8.8"},
        {"local_ip": "127.0.0.1"},
        {"local_ip": "not-an-ip"},
        {"local_port": 70000},
        {"connection_secret": "secret"},
        {"connection_secret": "1000000"},
        {"connection_type": "HTTP"},
    ],
)
def test_rejects_unsafe_or_invalid_lan_configuration(overrides):
    with pytest.raises(ZKTecoConfigurationError):
        ZKTecoLanConnector(config(**overrides), client_factory=FakeFactory())


def test_mb2000_user_id_must_be_numeric_and_at_most_nine_digits():
    connector = ZKTecoLanConnector(config(), client_factory=FakeFactory())
    with pytest.raises(ZKTecoConfigurationError):
        connector.create_user("student-1", "اسم")
    with pytest.raises(ZKTecoConfigurationError):
        connector.create_user("1234567890", "اسم")

import json

from bridge_core.adapters.base import DeviceCapability
from bridge_core.adapters.simulator import SimulatorConnector


def test_simulator_supports_roster_crud_and_capabilities(tmp_path):
    users_file = tmp_path / "users.json"
    users_file.write_text(
        json.dumps([{"external_user_id": "stu-1", "display_name": "قديم"}], ensure_ascii=False),
        encoding="utf-8",
    )
    connector = SimulatorConnector({"users_file": str(users_file)})

    assert connector.capabilities() == {
        DeviceCapability.READ_USERS,
        DeviceCapability.CREATE_USER,
        DeviceCapability.UPDATE_USER,
        DeviceCapability.DELETE_USER,
    }
    assert connector.read_users()[0]["external_user_id"] == "stu-1"
    assert connector.create_user("stu-2", "جديد")["result"] == "SUCCEEDED"
    assert connector.create_user("stu-2", "مكرر")["already_exists"] is True
    assert connector.update_user("stu-2", "محدث")["result"] == "SUCCEEDED"
    assert connector.delete_user("stu-2")["result"] == "SUCCEEDED"
    assert [user["external_user_id"] for user in connector.read_users()] == ["stu-1"]

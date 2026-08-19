"""إعداد الجسر — من bridge.json أو متغيرات البيئة (BRIDGE_*). لا أسرار في الكود."""

import json
import os
from pathlib import Path

DEFAULTS = {
    "saas_url": "",
    "credential": "",
    "queue_path": "bridge-queue.sqlite3",
    "heartbeat_seconds": 60,
    "batch_size": 200,
    "simulator_users_file": "",
}


def load_config(path: str | None = None) -> dict:
    config = dict(DEFAULTS)
    file_path = Path(path or os.environ.get("BRIDGE_CONFIG", "bridge.json"))
    if file_path.exists():
        config.update(json.loads(file_path.read_text(encoding="utf-8")))
    for key in DEFAULTS:
        env_value = os.environ.get(f"BRIDGE_{key.upper()}")
        if env_value:
            config[key] = env_value
    if not config["saas_url"] or not config["credential"]:
        raise SystemExit("الإعداد ناقص: saas_url وcredential مطلوبان (bridge.json أو BRIDGE_*).")
    return config

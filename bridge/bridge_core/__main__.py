"""تشغيل الجسر: ‏run (حلقة دائمة headless) أو run-once (دورة واحدة — للاختبار/E2E).

‏simulate: يضيف أحداث ملف JSON للطابور مباشرة (جهاز محاكاة) ثم يفرغ — تطوير فقط.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from bridge_core.client import SaaSClient
from bridge_core.config import load_config
from bridge_core.engine import BridgeEngine
from bridge_core.queue import DurableQueue


def _engine(config: dict) -> BridgeEngine:
    client = SaaSClient(base_url=config["saas_url"], credential=config["credential"])
    queue = DurableQueue(config["queue_path"])
    return BridgeEngine(
        client=client,
        queue=queue,
        batch_size=int(config["batch_size"]),
        simulator_users_file=config.get("simulator_users_file", ""),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bridge")
    parser.add_argument("command", choices=["run", "run-once", "simulate", "queue-status"])
    parser.add_argument("--config", default=None)
    parser.add_argument("--events-file", default=None, help="لأمر simulate")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    engine = _engine(config)

    if args.command == "queue-status":
        print(json.dumps(engine.queue.counts(), ensure_ascii=False))
        return 0
    if args.command == "simulate":
        events = json.loads(Path(args.events_file).read_text(encoding="utf-8"))
        added = sum(1 for event in events if engine.queue.enqueue(event))
        result = engine.flush()
        print(json.dumps({"queued": added, **result}, ensure_ascii=False))
        return 0
    if args.command == "run-once":
        print(json.dumps(engine.run_once(), ensure_ascii=False))
        return 0
    # run: حلقة دائمة — Windows Service يغلف هذا الأمر (Auto Start)
    interval = int(config["heartbeat_seconds"])
    while True:
        engine.run_once()
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())

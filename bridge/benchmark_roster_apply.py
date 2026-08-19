"""قياس تنفيذ أوامر القائمة على موصل المحاكاة (جانب الجسر) — 100/500/1000 أمر.

التشغيل: ‏python benchmark_roster_apply.py (من مجلد bridge، بأي Python 3.12+).
"""

import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bridge_core.adapters.simulator import SimulatorConnector  # noqa: E402


def run(sizes=(100, 500, 1000)) -> None:
    for size in sizes:
        with tempfile.TemporaryDirectory() as temp:
            connector = SimulatorConnector({"users_file": str(Path(temp) / "users.json")})
            durations = []
            t0 = time.perf_counter()
            for i in range(size):
                connector.create_user(f"stu-{i}", f"طالب {i}")
            create_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            for i in range(size):
                connector.update_user(f"stu-{i}", f"طالب معدل {i}")
            update_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            for i in range(size):
                connector.delete_user(f"stu-{i}")
            delete_ms = (time.perf_counter() - t0) * 1000

            assert connector.read_users() == []
            durations = [create_ms, update_ms, delete_ms]
            print(
                f"commands={size:5d} | create={create_ms:8.1f}ms | "
                f"update={update_ms:8.1f}ms | delete={delete_ms:8.1f}ms | "
                f"median-op={statistics.median(durations) / size:6.3f}ms/cmd"
            )


if __name__ == "__main__":
    run()

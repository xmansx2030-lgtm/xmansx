"""Run the Render single-instance production topology.

The persistent disk can only be attached to one Render service. Keeping the web,
worker, and scheduler processes in this service lets imports, private documents,
and local backup staging share that disk without exposing it over the network.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer") from exc
    if value < 1:
        raise SystemExit(f"{name} must be positive")
    return value


def _prepare_storage() -> None:
    for name in (
        "MEDIA_ROOT",
        "GENERATED_DOCUMENTS_ROOT",
        "DATABASE_BACKUP_ROOT",
        "BACKUP_STORAGE_LOCATION",
    ):
        value = os.environ.get(name)
        if value:
            Path(value).mkdir(parents=True, exist_ok=True)


def main() -> int:
    _prepare_storage()
    concurrency = str(_positive_int("CELERY_WORKER_CONCURRENCY", 1))
    beat_schedule = os.environ.get(
        "CELERY_BEAT_SCHEDULE_PATH", str(Path.cwd() / "celerybeat-schedule")
    )
    commands = {
        "web": [
            "gunicorn",
            "config.wsgi:application",
            "--config",
            "config/gunicorn.conf.py",
        ],
        "worker": [
            "celery",
            "-A",
            "config",
            "worker",
            "--loglevel=info",
            "--concurrency",
            concurrency,
            "--hostname",
            "render-worker@%h",
        ],
        "beat": [
            "celery",
            "-A",
            "config",
            "beat",
            "--loglevel=info",
            "--schedule",
            beat_schedule,
        ],
    }
    processes = {
        name: subprocess.Popen(command)  # noqa: S603
        for name, command in commands.items()
    }
    stopping = False

    def stop(_signum: int | None = None, _frame: object | None = None) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        for process in processes.values():
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    exit_code = 0
    try:
        while not stopping:
            for name, process in processes.items():
                result = process.poll()
                if result is not None:
                    print(f"Render process {name} exited with code {result}", flush=True)
                    exit_code = result or 1
                    stop()
                    break
            time.sleep(0.5)
    finally:
        stop()
        deadline = time.monotonic() + 20
        for process in processes.values():
            remaining = max(0.0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.kill()
        for process in processes.values():
            process.wait()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

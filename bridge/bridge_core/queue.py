"""طابور أحداث دائم على SQLite — لا اعتماد على RAM: انقطاع الإنترنت لا يفقد حدثًا.

الحالات: PENDING → SENT → ACKNOWLEDGED؛ الفشل القابل للإعادة يرجع FAILED_RETRYABLE.
لا يخزن إلا الحد الأدنى (هوية الجهاز/المستخدم الخارجي/الوقت/النوع) — لا بيانات
بيومترية إطلاقًا.
"""

import json
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS event_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

RETRYABLE = ("PENDING", "FAILED_RETRYABLE")


class DurableQueue:
    def __init__(self, path: str | Path):
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def enqueue(self, event: dict) -> bool:
        """يضيف حدثًا — التكرار المحلي يتجاهل (نفس المفتاح الحتمي)."""
        key = event.get("external_event_id") or "|".join(
            str(event.get(k, ""))
            for k in ("device_id", "external_user_id", "occurred_at", "event_type")
        )
        try:
            self._conn.execute(
                "INSERT INTO event_queue (dedupe_key, payload) VALUES (?, ?)",
                (f"{event.get('device_id')}::{key}", json.dumps(event, ensure_ascii=False)),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def next_batch(self, size: int) -> list[tuple[int, dict]]:
        rows = self._conn.execute(
            "SELECT id, payload FROM event_queue WHERE state IN (?, ?) ORDER BY id LIMIT ?",
            (*RETRYABLE, size),
        ).fetchall()
        return [(row[0], json.loads(row[1])) for row in rows]

    def mark(self, ids: list[int], state: str) -> None:
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        self._conn.execute(
            f"UPDATE event_queue SET state = ?, attempts = attempts + 1 "  # noqa: S608
            f"WHERE id IN ({placeholders})",
            (state, *ids),
        )
        self._conn.commit()

    def counts(self) -> dict:
        rows = self._conn.execute(
            "SELECT state, COUNT(*) FROM event_queue GROUP BY state"
        ).fetchall()
        return dict(rows)

    def close(self) -> None:
        self._conn.close()

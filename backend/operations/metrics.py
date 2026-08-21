"""Small process-local operational counters with bounded, low-cardinality labels."""

from collections import defaultdict
from threading import Lock


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: dict[tuple[str, str, str], dict[str, float]] = defaultdict(
            lambda: {"count": 0, "duration_ms": 0.0}
        )

    def observe_http(
        self, *, method: str, route: str, status_code: int, duration_ms: float
    ) -> None:
        status_class = f"{status_code // 100}xx"
        key = (method[:10], route[:160], status_class)
        with self._lock:
            bucket = self._requests[key]
            bucket["count"] += 1
            bucket["duration_ms"] += max(duration_ms, 0)

    def snapshot(self) -> dict:
        with self._lock:
            rows = []
            total = errors = 0
            duration = 0.0
            for (method, route, status_class), values in sorted(self._requests.items()):
                count = int(values["count"])
                total += count
                duration += values["duration_ms"]
                if status_class in {"4xx", "5xx"}:
                    errors += count
                rows.append(
                    {
                        "method": method,
                        "route": route,
                        "status_class": status_class,
                        "count": count,
                        "average_duration_ms": round(values["duration_ms"] / count, 1),
                    }
                )
        return {
            "request_count": total,
            "error_count": errors,
            "error_rate": round(errors / total, 4) if total else 0,
            "average_duration_ms": round(duration / total, 1) if total else 0,
            "series": rows,
        }

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()


registry = MetricsRegistry()

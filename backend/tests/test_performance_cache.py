"""Regression tests for cache pressure protections."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from unittest.mock import MagicMock, Mock, patch

import pytest

import common.cache as resilient_cache
import school_dashboard.cache as dashboard_cache
from common.cache import delete_if_value
from common.errors import ApiError
from operations.health import database_resource_usage, redis_resource_usage


class _Cache:
    def __init__(self, *, values=None, acquire_lock=True):
        self.values = values or {}
        self.acquire_lock = acquire_lock
        self.set_calls = []

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value, timeout=None):
        self.values[key] = value
        self.set_calls.append((key, value, timeout))

    def add(self, key, value, timeout=None):
        if not self.acquire_lock or key in self.values:
            return False
        self.values[key] = value
        return True


def test_dashboard_cache_populates_fresh_and_stale_values_under_one_lease(monkeypatch):
    fake_cache = _Cache()
    monkeypatch.setattr(dashboard_cache, "cache", fake_cache)
    builder = Mock(return_value={"current": True})

    result = dashboard_cache.cached(key="dash:1:today", ttl=15, builder=builder)

    assert result == {"current": True}
    assert builder.call_count == 1
    assert ("dash:1:today", {"current": True}, 15) in fake_cache.set_calls
    assert (
        "dash:1:today:stale",
        {"current": True},
        15 + dashboard_cache.STALE_GRACE_SECONDS,
    ) in fake_cache.set_calls


def test_dashboard_cache_serves_stale_value_while_another_request_refreshes(monkeypatch):
    fake_cache = _Cache(
        values={"dash:1:today:stale": {"current": "previous"}}, acquire_lock=False
    )
    monkeypatch.setattr(dashboard_cache, "cache", fake_cache)
    builder = Mock()

    result = dashboard_cache.cached(key="dash:1:today", ttl=15, builder=builder)

    assert result == {"current": "previous"}
    builder.assert_not_called()


def test_live_cache_uses_a_bounded_stale_grace(monkeypatch):
    fake_cache = _Cache()
    monkeypatch.setattr(dashboard_cache, "cache", fake_cache)

    dashboard_cache.cached(
        key="dash:1:attendance-monitoring",
        ttl=5,
        stale_grace_seconds=5,
        builder=lambda: {"current": True},
    )

    assert (
        "dash:1:attendance-monitoring:stale",
        {"current": True},
        10,
    ) in fake_cache.set_calls


@pytest.mark.django_db
def test_monitoring_pollers_share_one_school_scoped_cache_entry(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    payload = {
        "school_time": "2026-09-22T08:00:00+03:00",
        "date": "2026-09-22",
        "period": None,
        "alert": None,
        "summary": None,
        "sections": [],
    }

    with patch(
        "attendance.api.views.get_current_section_attendance_statuses",
        return_value=payload,
    ) as selector:
        first = client.get("/api/v1/attendance/monitoring/current/")
        second = client.get("/api/v1/attendance/monitoring/current/")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == payload
    selector.assert_called_once()


def test_performance_cache_outage_warning_is_rate_limited(monkeypatch):
    logger = Mock()
    monkeypatch.setattr(resilient_cache, "logger", logger)
    monkeypatch.setattr(resilient_cache, "_last_failure_log_at", -60.0)
    ticks = iter((0.0, 1.0, 60.0))
    monkeypatch.setattr(resilient_cache.time, "monotonic", lambda: next(ticks))

    resilient_cache._log_cache_unavailable()
    resilient_cache._log_cache_unavailable()
    resilient_cache._log_cache_unavailable()

    assert logger.warning.call_count == 2


def test_performance_cache_circuit_bounds_retries_and_invalidation(monkeypatch):
    backend = resilient_cache.ResilientRedisCache("redis://unused/0", {})
    monkeypatch.setattr(resilient_cache, "_retry_cache_at", 0.0)
    ticks = [10.0]
    monkeypatch.setattr(resilient_cache.time, "monotonic", lambda: ticks[0])
    monkeypatch.setattr(resilient_cache, "_log_cache_unavailable", Mock())
    failed = Mock(side_effect=OSError("synthetic unavailable"))
    assert backend._fallback(failed, None) is None
    assert backend._fallback(failed, None) is None
    assert failed.call_count == 1
    # A mutation still succeeds while this optional cache is unavailable.
    monkeypatch.setattr(dashboard_cache, "cache", backend)
    dashboard_cache.invalidate_school(900)
    ticks[0] = 12.1
    recovered = Mock(return_value="recovered")
    assert backend._fallback(recovered, None) == "recovered"
    recovered.assert_called_once()


def test_database_resource_usage_is_aggregate_only(monkeypatch):
    cursor = Mock()
    cursor.fetchone.return_value = (12, 3, 1)
    connection_mock = MagicMock()
    connection_mock.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr("operations.health.connection", connection_mock)

    result = database_resource_usage()

    assert result == {"connections": 12, "active_connections": 3, "waiting_connections": 1}
    query = cursor.execute.call_args.args[0]
    assert "pg_stat_activity" in query
    assert "query" not in query.lower()


def test_redis_resource_usage_returns_only_pressure_metrics(monkeypatch):
    monkeypatch.setattr("operations.health.unique_redis_urls", lambda: ("redis://synthetic/0",))
    client = Mock()
    client.info.side_effect = [
        {"used_memory": 100, "used_memory_peak": 140, "maxmemory": 1024},
        {"connected_clients": 4, "blocked_clients": 1},
    ]
    client.llen.side_effect = [2, 3, 4]
    monkeypatch.setattr("operations.health.redis.Redis.from_url", lambda *_args, **_kwargs: client)

    result = redis_resource_usage()

    assert result == {
        "used_memory_bytes": 100,
        "used_memory_peak_bytes": 140,
        "maxmemory_bytes": 1024,
        "connected_clients": 4,
        "blocked_clients": 1,
        "queue_depths": {"celery": 2, "imports": 3, "maintenance": 4},
    }


def test_long_running_jobs_do_not_store_duplicate_results_in_redis():
    from staff.tasks import process_staff_import_job
    from students.tasks import commit_student_import_job, process_import_job, run_purge_job

    assert process_staff_import_job.ignore_result is True
    assert process_import_job.ignore_result is True
    assert commit_student_import_job.ignore_result is True
    assert run_purge_job.ignore_result is True


class _AtomicCache(_Cache):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mutex = Lock()

    def get(self, *args, **kwargs):
        with self.mutex:
            return super().get(*args, **kwargs)

    def set(self, *args, **kwargs):
        with self.mutex:
            return super().set(*args, **kwargs)

    def add(self, *args, **kwargs):
        with self.mutex:
            return super().add(*args, **kwargs)

    def delete_if_value(self, key, expected):
        with self.mutex:
            if self.values.get(key) == expected:
                self.values.pop(key)
                return True
            return False


@pytest.mark.parametrize("outage", [False, True])
def test_slow_cold_fill_is_shared_instead_of_eight_fallback_builds(monkeypatch, outage):
    fake = _AtomicCache(acquire_lock=not outage)
    if outage:
        fake.is_available = lambda: False
        fake.set = lambda *_args, **_kwargs: False
    monkeypatch.setattr(dashboard_cache, "cache", fake)
    gate = Barrier(8)
    builder = Mock(side_effect=lambda: (time.sleep(1.25), {"school": 1})[1])

    def request(_):
        gate.wait()
        return dashboard_cache.cached(key="dash:1:slow", ttl=15, builder=builder)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(request, range(8)))
    assert results == [{"school": 1}] * 8
    assert builder.call_count == 1


def test_cold_lease_wait_expires_without_starting_another_builder(monkeypatch, settings):
    fake = _AtomicCache(acquire_lock=False)
    monkeypatch.setattr(dashboard_cache, "cache", fake)
    settings.DASHBOARD_CACHE_WAIT_SECONDS = 0.05
    builder = Mock()
    with pytest.raises(ApiError) as error:
        dashboard_cache.cached(key="dash:1:busy", ttl=15, builder=builder)
    assert error.value.code == "DATA_REFRESH_BUSY"
    assert error.value.status_code == 503
    builder.assert_not_called()


def test_builder_error_releases_its_lease_and_allows_a_later_refresh(monkeypatch):
    fake = _AtomicCache()
    monkeypatch.setattr(dashboard_cache, "cache", fake)
    with pytest.raises(RuntimeError, match="synthetic"):
        dashboard_cache.cached(
            key="dash:1:failure", ttl=15, builder=Mock(side_effect=RuntimeError("synthetic"))
        )
    recovered = dashboard_cache.cached(
        key="dash:1:failure", ttl=15, builder=lambda: "recovered"
    )
    assert recovered == "recovered"


def test_real_redis_lease_release_cannot_delete_a_successor():
    from django.core.cache import cache
    cache.set("pressure:lease", "successor", timeout=30)
    assert delete_if_value(cache, "pressure:lease", "expired-owner") is False
    assert cache.get("pressure:lease") == "successor"
    assert delete_if_value(cache, "pressure:lease", "successor") is True

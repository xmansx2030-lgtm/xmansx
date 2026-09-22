"""Static regression gates for the high-concurrency Render topology."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _env_map(service: dict) -> dict[str, dict]:
    return {item["key"]: item for item in service["envVars"]}


def test_scalable_blueprint_separates_cache_security_and_queue_redis():
    blueprint = yaml.safe_load((ROOT / "render.scalable.yaml").read_text(encoding="utf-8"))
    services = {service["name"]: service for service in blueprint["services"]}

    cache = services["xmansx-scalable-cache"]
    assert cache["maxmemoryPolicy"] == "allkeys-lru"
    assert cache["persistenceMode"] == "off"

    for name in ("xmansx-scalable-security", "xmansx-scalable-redis"):
        assert services[name]["maxmemoryPolicy"] == "noeviction"
        assert services[name]["persistenceMode"] == "journal-snapshot"

    core_env = _env_map(services["xmansx-scalable-core"])
    assert core_env["CACHE_REDIS_URL"]["fromService"]["name"] == "xmansx-scalable-cache"
    assert (
        core_env["SECURITY_REDIS_URL"]["fromService"]["name"]
        == "xmansx-scalable-security"
    )
    assert core_env["CELERY_BROKER_URL"]["fromService"]["name"] == "xmansx-scalable-redis"


def test_scalable_web_pool_is_bounded_per_replica():
    blueprint = yaml.safe_load((ROOT / "render.scalable.yaml").read_text(encoding="utf-8"))
    core = next(
        service for service in blueprint["services"] if service["name"] == "xmansx-scalable-core"
    )
    env = _env_map(core)

    assert core["numInstances"] == 2
    assert env["GUNICORN_WORKERS"]["value"] == "2"
    assert env["GUNICORN_THREADS"]["value"] == "4"
    assert env["DATABASE_POOL_ENABLED"]["value"] == "true"
    assert env["DATABASE_POOL_MIN_SIZE"]["value"] == "1"
    assert env["DATABASE_POOL_MAX_SIZE"]["value"] == "4"

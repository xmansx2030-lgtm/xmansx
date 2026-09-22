"""PostgreSQL connection settings shared by local and production environments."""

from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, env_int, env_str


def postgres_database(*, production: bool) -> dict:
    """Build one bounded PostgreSQL configuration.

    Django creates a separate psycopg pool in every process. Keeping the pool
    sizes explicit prevents horizontal web/worker scaling from exhausting the
    database connection limit. Deployments that use an external pooler can
    leave ``DATABASE_POOL_ENABLED`` disabled and tune ``CONN_MAX_AGE`` instead.
    """

    pool_enabled = env_bool("DATABASE_POOL_ENABLED", False)
    connect_timeout = env_int("DATABASE_CONNECT_TIMEOUT_SECONDS", 5)
    if connect_timeout < 1:
        raise ImproperlyConfigured("DATABASE_CONNECT_TIMEOUT_SECONDS must be positive")

    options: dict = {"connect_timeout": connect_timeout}
    if pool_enabled:
        min_size = env_int("DATABASE_POOL_MIN_SIZE", 1)
        max_size = env_int("DATABASE_POOL_MAX_SIZE", 4)
        timeout = env_int("DATABASE_POOL_TIMEOUT_SECONDS", 5)
        max_idle = env_int("DATABASE_POOL_MAX_IDLE_SECONDS", 300)
        max_lifetime = env_int("DATABASE_POOL_MAX_LIFETIME_SECONDS", 1800)
        if min_size < 0 or max_size < 1 or min_size > max_size:
            raise ImproperlyConfigured(
                "DATABASE_POOL_MIN_SIZE must be non-negative and no greater than "
                "DATABASE_POOL_MAX_SIZE"
            )
        if min(timeout, max_idle, max_lifetime) < 1:
            raise ImproperlyConfigured("Database pool timeouts must be positive")
        options["pool"] = {
            "min_size": min_size,
            "max_size": max_size,
            "timeout": timeout,
            "max_idle": max_idle,
            "max_lifetime": max_lifetime,
        }

    def value(name: str, default):
        return env_str(name) if production else env_str(name, default)

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": value("POSTGRES_DB", "xmansx"),
        "USER": value("POSTGRES_USER", "xmansx"),
        "PASSWORD": value("POSTGRES_PASSWORD", "xmansx-dev"),
        "HOST": value("POSTGRES_HOST", "localhost"),
        # Docker publishes PostgreSQL on host port 5433; containers override it.
        "PORT": env_int("POSTGRES_PORT", 5432 if production else 5433),
        # Django requires zero persistent age when psycopg's pool is enabled.
        "CONN_MAX_AGE": 0 if pool_enabled else env_int("DATABASE_CONN_MAX_AGE", 60),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": options,
    }

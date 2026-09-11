"""PostgreSQL row-level tenant context.

Production connections enable the policies by default.  Every request or
background job must then choose exactly one school, or an explicit platform
bypass.  An unset context is deliberately fail-closed.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection


def _settings() -> tuple[str, str, str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('app.current_school_id', true), "
            "current_setting('app.current_user_id', true), "
            "current_setting('app.rls_bypass', true)"
        )
        school_id, user_id, bypass = cursor.fetchone()
    return school_id or "", user_id or "", bypass or ""


def set_tenant_context(
    *, school_id: int | None = None, user_id: int | None = None, bypass: bool = False
) -> None:
    """Set connection-local tenant state using bound values only."""
    if school_id is not None and bypass:
        raise ValueError("A tenant context cannot be scoped and bypassed together")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.current_school_id', %s, false), "
            "set_config('app.current_user_id', %s, false), "
            "set_config('app.rls_bypass', %s, false)",
            [
                str(school_id) if school_id is not None else "",
                str(user_id) if user_id is not None else "",
                "on" if bypass else "off",
            ],
        )


def clear_tenant_context() -> None:
    set_tenant_context()


@contextmanager
def tenant_context(
    *, school_id: int | None = None, user_id: int | None = None, bypass: bool = False
) -> Iterator[None]:
    """Temporarily scope ORM access and restore any outer context."""
    previous_school, previous_user, previous_bypass = _settings()
    set_tenant_context(school_id=school_id, user_id=user_id, bypass=bypass)
    try:
        yield
    finally:
        set_tenant_context(
            school_id=int(previous_school) if previous_school else None,
            user_id=int(previous_user) if previous_user else None,
            bypass=previous_bypass == "on",
        )

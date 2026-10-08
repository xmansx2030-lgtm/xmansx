"""Exact audited deletion scope; never grants credential or general recovery access."""

from contextlib import contextmanager

from django.db import connection

from common.tenant_rls import can_restore_tenant_context

_KEYS = (
    "app.current_school_id",
    "app.recovery_purge_kind",
    "app.recovery_purge_school",
    "app.recovery_purge_student",
    "app.recovery_purge_actor",
    "app.recovery_purge_job",
)


@contextmanager
def recovery_purge_scope(*, school_id, actor_id, student_id=None, job_id=None):
    if not connection.in_atomic_block:
        raise RuntimeError("Recovery metadata purge requires an atomic transaction")
    # Legacy internal callers with no verified actor get no additional authority.
    # Database policies validate current role, exact school/student and optional job.
    if actor_id is None:
        yield
        return
    values = (
        str(school_id),
        "STUDENT" if student_id is not None else "SCHOOL",
        str(school_id),
        str(student_id) if student_id is not None else "",
        str(actor_id),
        str(job_id) if job_id is not None else "",
    )
    with connection.cursor() as cursor:
        previous = []
        for key, value in zip(_KEYS, values, strict=True):
            cursor.execute("SELECT current_setting(%s, true)", [key])
            previous.append(cursor.fetchone()[0] or "")
            cursor.execute("SELECT set_config(%s, %s, true)", [key, value])
    try:
        yield
    finally:
        if can_restore_tenant_context():
            with connection.cursor() as cursor:
                for key, value in zip(_KEYS, previous, strict=True):
                    cursor.execute("SELECT set_config(%s, %s, true)", [key, value])

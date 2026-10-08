"""حذف مستأجر كامل نهائيًا من لوحة المنصة.

الحذف يشمل كل نموذج يحمل مرجعًا مباشرًا للمدرسة، بترتيب التبعيات، ثم المدرسة
نفسها. تُجمع مفاتيح الملفات قبل حذف قاعدة البيانات وتُحذف من التخزين بعد نجاح
المعاملة. حساب المستخدم العالمي لا يُحذف إذا كان مرتبطًا بمدرسة أخرى أو كان
حساب إدارة منصة.
"""

import logging
from dataclasses import dataclass

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection, models, transaction
from django.db.models.deletion import ProtectedError

from audit.models import AuditAction, AuditLog
from audit.services import record_event
from common.errors import ApiError
from common.tenant_rls import tenant_context
from memberships.models import SchoolMembership
from platform_team.access import PlatformCapability, has_platform_capability
from schools.models import School

logger = logging.getLogger("xmansx.school_purge")


@dataclass(frozen=True)
class SchoolScopedModel:
    model: type[models.Model]
    school_field: models.Field


def school_scoped_models_in_delete_order() -> list[SchoolScopedModel]:
    """يعيد النماذج التابعة للمدرسة من الأكثر اعتمادًا إلى الأقل."""
    scoped: dict[type[models.Model], models.Field] = {}
    for model in apps.get_models():
        for field in model._meta.concrete_fields:
            if getattr(getattr(field, "remote_field", None), "model", None) is School:
                scoped[model] = field
                break

    dependencies: dict[type[models.Model], set[type[models.Model]]] = {
        model: set() for model in scoped
    }
    for model in scoped:
        for field in model._meta.concrete_fields:
            target = getattr(getattr(field, "remote_field", None), "model", None)
            if target in scoped and target is not model:
                dependencies[model].add(target)

    remaining = set(scoped)
    ordered: list[type[models.Model]] = []
    while remaining:
        # A -> B تعني أن A يشير إلى B؛ نحذف أولًا عقدة لا يشير إليها نموذج آخر.
        ready = sorted(
            (
                model
                for model in remaining
                if not any(model in dependencies[other] for other in remaining)
            ),
            key=lambda model: model._meta.label_lower,
        )
        if not ready:
            labels = ", ".join(sorted(model._meta.label for model in remaining))
            raise RuntimeError(f"Circular school purge dependencies: {labels}")
        ordered.extend(ready)
        remaining.difference_update(ready)

    return [SchoolScopedModel(model=model, school_field=scoped[model]) for model in ordered]


def _storage_objects(school_id: int, scoped_models: list[SchoolScopedModel]):
    found: list[tuple[object, str]] = []
    seen: set[tuple[int, str]] = set()
    for scoped in scoped_models:
        file_fields = [
            field
            for field in scoped.model._meta.concrete_fields
            if isinstance(field, models.FileField)
        ]
        if not file_fields:
            continue
        queryset = scoped.model._default_manager.filter(
            **{scoped.school_field.attname: school_id}
        )
        for field in file_fields:
            for name in queryset.exclude(**{field.name: ""}).values_list(
                field.name, flat=True
            ):
                if not name:
                    continue
                key = (id(field.storage), name)
                if key not in seen:
                    seen.add(key)
                    found.append((field.storage, name))
    return found


def _delete_school_audit_logs(school_id: int):
    """Open the audit DELETE policy for this school and this transaction only."""
    if not connection.in_atomic_block:
        raise RuntimeError("School audit deletion requires an atomic school purge")
    if connection.vendor != "postgresql":
        return AuditLog.objects.filter(school_id=school_id).delete()

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.school_purge_id', true)")
        previous_scope = cursor.fetchone()[0] or ""
        cursor.execute(
            "SELECT set_config('app.school_purge_id', %s, true)", [str(school_id)]
        )
    try:
        result = AuditLog.objects.filter(school_id=school_id).delete()
        # RLS can silently filter a DELETE. Never continue after an incomplete purge.
        if AuditLog.objects.filter(school_id=school_id).exists():
            raise ApiError(
                "SCHOOL_DELETE_BLOCKED",
                "تعذر إكمال حذف سجلات المدرسة؛ لم يتم حذف أي بيانات.",
                status_code=409,
            )
        return result
    finally:
        # A failed database statement is rolled back by the enclosing atomic block.
        # On success restore immediately, including when a caller owns a larger transaction.
        if not connection.needs_rollback:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.school_purge_id', %s, true)", [previous_scope]
                )


def permanently_delete_school(*, school_id: int, confirmation_name: str, actor, request=None):
    """يحذف المدرسة وبياناتها، ويعيد ملخصًا صريحًا لنتيجة التخزين."""
    if not has_platform_capability(actor, PlatformCapability.SCHOOLS_MANAGE):
        raise ApiError(
            "PERMISSION_DENIED",
            "لا تملك صلاحية حذف المدارس من المنصة.",
            status_code=403,
        )
    scoped_models = school_scoped_models_in_delete_order()
    storage_objects: list[tuple[object, str]] = []
    database_records_deleted = 0
    deleted_user_accounts = 0

    try:
        with transaction.atomic():
            school = School.objects.select_for_update().get(id=school_id)
            if confirmation_name.strip() != school.name:
                raise ApiError(
                    "SCHOOL_DELETE_CONFIRMATION_MISMATCH",
                    "اسم المدرسة المدخل لا يطابق اسم المدرسة.",
                    status_code=409,
                )

            deleted_school_name = school.name
            member_user_ids = list(
                SchoolMembership.objects.filter(school=school).values_list(
                    "user_id", flat=True
                )
            )
            from parents.recovery_purge import recovery_purge_scope

            # Recovery review metadata deliberately ignores ordinary platform RLS
            # bypass. This exact deletion purpose is checked again by PostgreSQL.
            with (
                tenant_context(user_id=actor.id, bypass=True),
                recovery_purge_scope(school_id=school.id, actor_id=actor.id),
            ):
                storage_objects = _storage_objects(school.id, scoped_models)

                for scoped in scoped_models:
                    if scoped.model is AuditLog:
                        deleted, _ = _delete_school_audit_logs(school.id)
                    else:
                        deleted, _ = scoped.model._default_manager.filter(
                            **{scoped.school_field.attname: school.id}
                        ).delete()
                    database_records_deleted += deleted

                deleted, _ = school.delete()
                database_records_deleted += deleted

            User = get_user_model()
            orphan_ids = list(
                User.objects.filter(id__in=member_user_ids, memberships__isnull=True)
                .filter(
                    is_superuser=False,
                    is_staff=False,
                    platform_staff_membership__isnull=True,
                )
                .values_list("id", flat=True)
            )
            # A global employee account may still follow children at another school.
            from parents.models import GuardianStudentRelation

            guardian_user_ids = set(
                GuardianStudentRelation.objects.filter(user_id__in=orphan_ids)
                .values_list("user_id", flat=True)
            )
            orphan_ids = [user_id for user_id in orphan_ids if user_id not in guardian_user_ids]
            if orphan_ids:
                User.objects.filter(id__in=orphan_ids).delete()
                deleted_user_accounts = len(orphan_ids)

            # يبقى سجل منصة بلا FK للمدرسة المحذوفة وبلا اسم أو بيانات شخصية.
            record_event(
                AuditAction.PLATFORM_SCHOOL_PERMANENTLY_DELETED,
                request=request,
                actor=actor,
                target_type="School",
                target_id=school_id,
                metadata={
                    "database_records_deleted": database_records_deleted,
                    "user_accounts_deleted": deleted_user_accounts,
                    "storage_objects_queued": len(storage_objects),
                },
            )
    except School.DoesNotExist as exc:
        raise ApiError(
            "NOT_FOUND", "المدرسة المطلوبة غير موجودة.", status_code=404
        ) from exc
    except ProtectedError as exc:
        raise ApiError(
            "SCHOOL_DELETE_BLOCKED",
            "تعذر الحذف لأن بيانات مرتبطة بالمدرسة ما زالت محمية.",
            status_code=409,
        ) from exc

    storage_objects_deleted = 0
    storage_objects_failed = 0
    for storage, name in storage_objects:
        try:
            storage.delete(name)
            storage_objects_deleted += 1
        except Exception:
            logger.exception("school purge: storage object deletion failed")
            storage_objects_failed += 1

    return {
        "deleted": True,
        "school_id": school_id,
        "school_name": deleted_school_name,
        "database_records_deleted": database_records_deleted,
        "user_accounts_deleted": deleted_user_accounts,
        "storage_objects_deleted": storage_objects_deleted,
        "storage_objects_failed": storage_objects_failed,
    }

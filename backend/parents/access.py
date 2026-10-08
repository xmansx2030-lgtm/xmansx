"""Owned relation discovery then school-scoped access; never a global student bypass."""

from contextlib import contextmanager

from django.db import connection, transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from accounts.api.views import require_password_changed
from common.errors import ApiError
from common.tenant_rls import tenant_context
from parents.models import GuardianStudentRelation, RelationStatus
from schools.models import SchoolStatus
from subscriptions.access import BLOCKED, FULL, get_school_access_mode


def not_found():
    return ApiError("NOT_FOUND", "المورد المطلوب غير موجود.", status_code=404)


def lock_parent_school(school_id: int) -> None:
    """Take the school FK lock before child locks; Noor uses school FOR UPDATE first."""
    if not connection.in_atomic_block:
        raise RuntimeError("Parent school locks require an atomic transaction")
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM schools_school WHERE id = %s FOR KEY SHARE", [school_id])
        if cursor.fetchone() is None:
            raise not_found()


class ParentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        require_password_changed(request.user)


def owned_relation_index(user):
    # Only identifiers/status are read in global user scope. No student joins.
    with tenant_context(user_id=user.id):
        return list(
            GuardianStudentRelation.objects.filter(user=user)
            .order_by("id")
            .values(
                "id",
                "school_id",
                "student_id",
                "status",
            )
        )


@contextmanager
def parent_scope(user, relation_id: int, *, write: bool = False, lock: bool = False):
    require_password_changed(user)
    with tenant_context(user_id=user.id):
        index = (
            GuardianStudentRelation.objects.filter(id=relation_id, user=user)
            .values(
                "school_id",
                "student_id",
            )
            .first()
        )
    if index is None:
        raise not_found()
    with tenant_context(school_id=index["school_id"], user_id=user.id), transaction.atomic():
        if write or lock:
            # Match Noor's school then student order without serializing other parents.
            lock_parent_school(index["school_id"])
            from students.models import Student

            Student.objects.select_for_update().filter(
                school_id=index["school_id"],
                id=index["student_id"],
            ).first()
        queryset = GuardianStudentRelation.objects.filter(
            id=relation_id,
            user=user,
            school_id=index["school_id"],
            status=RelationStatus.ACTIVE,
        )
        if write or lock:
            queryset = queryset.select_for_update(of=("self",))
        relation = queryset.select_related("school", "student").first()
        if relation is None or relation.student.school_id != relation.school_id:
            raise not_found()
        if relation.contact_bound and (
            relation.contact_revision != relation.student.guardian_contact_revision
        ):
            raise not_found()
        if relation.student.merged_into_id is not None:
            raise not_found()
        if relation.school.status != SchoolStatus.ACTIVE:
            raise ApiError("SCHOOL_SUSPENDED", "المدرسة غير متاحة حالياً.", status_code=403)
        mode = get_school_access_mode(relation.school)
        if mode == BLOCKED:
            raise ApiError("SCHOOL_SUSPENDED", "المدرسة غير متاحة حالياً.", status_code=403)
        if write and mode != FULL:
            raise ApiError(
                "SUBSCRIPTION_WRITE_BLOCKED",
                "اشتراك المدرسة لا يسمح بطلبات جديدة.",
                status_code=403,
            )
        yield relation

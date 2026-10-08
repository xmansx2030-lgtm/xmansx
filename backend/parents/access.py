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


def relation_school_groups(index):
    """Group an owned index without changing the API's original relation order."""
    groups = {}
    for item in index:
        groups.setdefault(item["school_id"], []).append(item)
    return groups.items()


class ParentSchoolRead:
    """Request-local projection checks inside one exact school RLS context."""

    def __init__(self, user, school_id, owned_ids):
        self.user = user
        self.school_id = school_id
        self.owned_ids = owned_ids
        self.school_name = "المدرسة"

    def current_relations(self):
        from schools.models import School

        relations = list(
            GuardianStudentRelation.objects.filter(
                id__in=self.owned_ids, user=self.user, school_id=self.school_id,
                status=RelationStatus.ACTIVE,
            ).select_related("school", "student").order_by("id")
        )
        school = (
            relations[0].school if relations
            else School.objects.filter(id=self.school_id).first()
        )
        if school is None:
            return {}
        self.school_name = school.name
        if not relations or school.status != SchoolStatus.ACTIVE:
            return {}
        if get_school_access_mode(school) == BLOCKED:
            return {}
        return {
            relation.pk: relation for relation in relations
            if relation.student.school_id == self.school_id
            and relation.student.merged_into_id is None
            and (
                not relation.contact_bound
                or relation.contact_revision == relation.student.guardian_contact_revision
            )
        }


@contextmanager
def parent_school_read(user, school_id, relation_ids):
    """Batch owned reads only; writes retain their existing per-relation transaction.

    Prove ownership before choosing school context, even for a forged caller index.
    Do not wrap siblings in one transaction: retaining their warning locks together
    would introduce cross-guardian lock-order cycles in notification catch-up.
    """
    require_password_changed(user)
    with tenant_context(user_id=user.id):
        owned_ids = list(
            GuardianStudentRelation.objects.filter(
                id__in=relation_ids, user=user, school_id=school_id,
            ).values_list("id", flat=True)
        )
    if not owned_ids:
        raise not_found()
    with tenant_context(school_id=school_id, user_id=user.id):
        yield ParentSchoolRead(user, school_id, owned_ids)


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

"""واجهات دورة حياة الطالب والحذف النهائي.

الحذف (فردي/جماعي/معاينة): SCHOOL_MANAGER حصرًا — لا DELETE بسيط بل action
صريح باسم purge. قائمة غير النشطين: قراءة للمدير والوكيل.
"""

from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework import status as http_status
from rest_framework.request import Request
from rest_framework.response import Response

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from common.pagination import DefaultPagination
from memberships.api_base import SETTINGS_WRITE_ROLES, SchoolScopedAPIView
from memberships.models import SchoolRole
from students.models import Student, StudentPurgeJob, StudentStatus
from students.services import lifecycle as lifecycle_service
from students.services import purge as purge_service
from students.tasks import run_purge_job

INACTIVE_READ_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            StudentStatus.ACTIVE, StudentStatus.GRADUATED, StudentStatus.TRANSFERRED,
            StudentStatus.WITHDRAWN, StudentStatus.INACTIVE,
        ]
    )
    exit_date = serializers.DateField(required=False, allow_null=True)
    exit_reason = serializers.CharField(
        max_length=300, required=False, allow_blank=True, default=""
    )


class BulkStatusSerializer(StatusChangeSerializer):
    student_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), min_length=1, max_length=2000
    )


class PurgeSelectionSerializer(serializers.Serializer):
    student_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), min_length=1, max_length=2000
    )


class PurgeConfirmSerializer(serializers.Serializer):
    confirmation_token = serializers.CharField(max_length=64)
    reason = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


def _serialize_inactive_student(student) -> dict:
    enrollment = student.all_enrollments[0] if student.all_enrollments else None
    return {
        "id": student.id,
        "full_name": student.full_name,
        "national_id_masked": student.national_id_masked,
        "status": student.status,
        "exit_date": student.exit_date.isoformat() if student.exit_date else None,
        "exit_reason": student.exit_reason,
        "grade": {"name": enrollment.grade.name} if enrollment else None,
        "section": {"name": enrollment.section.name} if enrollment else None,
    }


class InactiveStudentsView(SchoolScopedAPIView):
    """الطلاب غير النشطين — مع فلتر «غير الموجودين في آخر ملف نور»."""

    read_roles = INACTIVE_READ_ROLES
    write_roles = SETTINGS_WRITE_ROLES

    def get(self, request: Request) -> Response:
        from django.db.models import Prefetch

        from students.models import StudentEnrollment

        def base_queryset():
            # آخر قيد (بأي حالة) — قيود غير النشطين مغلقة
            return Student.objects.filter(school=request.school).prefetch_related(
                Prefetch(
                    "enrollments",
                    queryset=StudentEnrollment.objects.select_related(
                        "grade", "section"
                    ).order_by("-id"),
                    to_attr="all_enrollments",
                )
            ).order_by("full_name")

        if request.query_params.get("missing_last_import"):
            from students.models import ImportJobStatus, StudentImportJob

            last_job = (
                StudentImportJob.objects.filter(
                    school=request.school, status=ImportJobStatus.COMPLETED
                )
                .order_by("-id")
                .first()
            )
            missing_ids = (
                [m["student_id"] for m in last_job.summary.get("missing_names", [])]
                if last_job
                else []
            )
            # المفقودون قد يكونون نشطين بعد (لم يصنفوا) — يعرضون للمراجعة
            queryset = base_queryset().filter(id__in=missing_ids)
        else:
            queryset = base_queryset().exclude(status=StudentStatus.ACTIVE)
            status_filter = request.query_params.get("status", "").strip()
            if status_filter:
                queryset = queryset.filter(status=status_filter)

        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(full_name__icontains=search)

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(
            [_serialize_inactive_student(s) for s in page]
        )


class StudentStatusView(SchoolScopedAPIView):
    read_roles = SETTINGS_WRITE_ROLES
    write_roles = SETTINGS_WRITE_ROLES

    def post(self, request: Request, student_id: int) -> Response:
        student = get_object_or_404(Student, id=student_id, school=request.school)
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lifecycle_service.set_student_status(
            student=student,
            new_status=serializer.validated_data["status"],
            actor=request.user,
            exit_date=serializer.validated_data.get("exit_date"),
            exit_reason=serializer.validated_data.get("exit_reason", ""),
            request=request,
        )
        return Response({"id": student.id, "status": student.status})


class BulkStatusView(SchoolScopedAPIView):
    read_roles = SETTINGS_WRITE_ROLES
    write_roles = SETTINGS_WRITE_ROLES

    def post(self, request: Request) -> Response:
        serializer = BulkStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        count = lifecycle_service.bulk_set_status(
            school=request.school,
            actor=request.user,
            student_ids=serializer.validated_data["student_ids"],
            new_status=serializer.validated_data["status"],
            exit_reason=serializer.validated_data.get("exit_reason", ""),
            request=request,
        )
        return Response({"updated": count, "status": serializer.validated_data["status"]})


class StudentPurgeView(SchoolScopedAPIView):
    """حذف فردي نهائي — action صريح، مدير فقط، مع ملخص خادمي وتأكيد سبق في الواجهة."""

    read_roles = SETTINGS_WRITE_ROLES
    write_roles = SETTINGS_WRITE_ROLES

    def post(self, request: Request, student_id: int) -> Response:
        student = get_object_or_404(Student, id=student_id, school=request.school)
        if student.status == StudentStatus.ACTIVE:
            raise ApiError(
                "STUDENT_ACTIVE_CANNOT_PURGE",
                "لا يمكن الحذف النهائي لطالب نشط — غيّر حالته أولاً.",
                status_code=409,
            )
        db_rows, storage_ok, storage_failed = purge_service.purge_student(student)
        record_event(
            AuditAction.STUDENT_PERMANENTLY_PURGED,
            request=request,
            actor=request.user,
            school=request.school,
            metadata={  # لا اسم/هوية/جوال/رقم طالب — أعداد فقط
                "records_deleted_count": db_rows,
                "storage_objects_deleted_count": storage_ok,
                "storage_objects_failed_count": storage_failed,
            },
        )
        return Response(
            {
                "deleted": True,
                "database_records": db_rows,
                "storage_objects_deleted": storage_ok,
                "storage_objects_failed": storage_failed,
            }
        )


class PurgePreviewView(SchoolScopedAPIView):
    read_roles = SETTINGS_WRITE_ROLES
    write_roles = SETTINGS_WRITE_ROLES

    def post(self, request: Request) -> Response:
        serializer = PurgeSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        preview = purge_service.create_purge_preview(
            school=request.school,
            actor=request.user,
            student_ids=serializer.validated_data["student_ids"],
        )
        return Response(preview)


def _serialize_purge_job(job: StudentPurgeJob) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "reason": job.reason,
        "total_students": job.total_students,
        "processed_students": job.processed_students,
        "deleted_students": job.deleted_students,
        "failed_students": job.failed_students,
        "db_records_deleted": job.db_records_deleted,
        "storage_objects_deleted": job.storage_objects_deleted,
        "storage_objects_failed": job.storage_objects_failed,
    }


class PurgeCreateView(SchoolScopedAPIView):
    read_roles = SETTINGS_WRITE_ROLES
    write_roles = SETTINGS_WRITE_ROLES

    def post(self, request: Request) -> Response:
        serializer = PurgeConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = purge_service.create_purge_job(
            school=request.school,
            actor=request.user,
            confirmation_token=serializer.validated_data["confirmation_token"],
            reason=serializer.validated_data.get("reason", ""),
            request=request,
        )
        run_purge_job.delay(job.id)
        return Response(_serialize_purge_job(job), status=http_status.HTTP_202_ACCEPTED)


class PurgeJobView(SchoolScopedAPIView):
    read_roles = SETTINGS_WRITE_ROLES
    write_roles = SETTINGS_WRITE_ROLES

    def get(self, request: Request, job_id: int) -> Response:
        job = get_object_or_404(StudentPurgeJob, id=job_id, school=request.school)
        return Response(_serialize_purge_job(job))

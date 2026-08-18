"""واجهات دليل الموظفين والاستيراد.

الصلاحيات: MANAGER = إدارة كاملة؛ VICE = قراءة الدليل الأساسي (جوال مقنع)؛
COUNSELOR/TEACHER محجوبان. التفاصيل بالجوال الكامل للمدير فقط (سياسة موثقة).
لا يكشف أي endpoint مدارس المستخدم الأخرى أو أدواره فيها.
"""

from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework import status as http_status
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.mobile import mask_mobile
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from common.excel_security import read_headers, validate_upload
from common.pagination import DefaultPagination
from memberships.api_base import SETTINGS_WRITE_ROLES, SchoolScopedAPIView
from memberships.models import SchoolRole
from staff.models import StaffImportJob, StaffImportStatus, StaffProfile
from staff.services import management
from staff.services.directory import staff_queryset
from staff.services.imports import commit as commit_service
from staff.services.imports import mapping as mapping_service
from staff.tasks import process_staff_import_job

MANAGER_ONLY = SETTINGS_WRITE_ROLES
DIRECTORY_READ_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)


class StaffPatchSerializer(serializers.Serializer):
    """حقول الملف الوظيفي فقط — لا school/user/membership (منع mass assignment)."""

    display_name = serializers.CharField(max_length=200, required=False)
    employee_number = serializers.CharField(
        max_length=30, required=False, allow_null=True, allow_blank=True
    )
    job_title = serializers.CharField(max_length=100, required=False, allow_blank=True)


def _serialize_staff(profile: StaffProfile, *, full_mobile: bool) -> dict:
    membership = profile.membership
    user = membership.user
    return {
        "id": profile.id,
        "display_name": profile.display_name,
        "employee_number": profile.employee_number,
        "job_title": profile.job_title,
        "mobile": user.mobile if full_mobile else mask_mobile(user.mobile),
        "roles": membership.role_codes(),
        "membership_status": membership.status,
        "joined_at": membership.joined_at.date().isoformat(),
        "is_active": profile.is_active,
    }


class StaffListView(SchoolScopedAPIView):
    read_roles = DIRECTORY_READ_ROLES
    write_roles = MANAGER_ONLY

    def get(self, request: Request) -> Response:
        queryset = staff_queryset(
            school=request.school,
            search=request.query_params.get("search", "").strip(),
            role=request.query_params.get("role", "").strip(),
            status=request.query_params.get("status", "").strip(),
        )
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request)
        # القائمة: جوال مقنع دائمًا (حتى للمدير) — الكامل في التفاصيل فقط
        return paginator.get_paginated_response(
            [_serialize_staff(p, full_mobile=False) for p in page]
        )


class StaffDetailView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY  # التفاصيل (بجوال كامل) للمدير فقط — سياسة موثقة
    write_roles = MANAGER_ONLY

    def get_object(self, request, staff_id: int) -> StaffProfile:
        return get_object_or_404(
            StaffProfile.objects.select_related("membership__user").prefetch_related(
                "membership__roles"
            ),
            id=staff_id,
            school=request.school,
        )

    def get(self, request: Request, staff_id: int) -> Response:
        profile = self.get_object(request, staff_id)
        return Response(_serialize_staff(profile, full_mobile=True))

    def patch(self, request: Request, staff_id: int) -> Response:
        profile = self.get_object(request, staff_id)
        serializer = StaffPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changed = []
        for field, value in serializer.validated_data.items():
            if field == "employee_number" and value == "":
                value = None
            if getattr(profile, field) != value:
                setattr(profile, field, value)
                changed.append(field)
        if changed:
            profile.save()
            record_event(
                AuditAction.STAFF_PROFILE_UPDATED,
                request=request, actor=request.user, school=request.school,
                target_type="SchoolMembership", target_id=profile.membership_id,
                metadata={"changed_fields": changed},
            )
        return Response(_serialize_staff(profile, full_mobile=True))


class StaffRolesView(StaffDetailView):
    def post(self, request: Request, staff_id: int) -> Response:
        profile = self.get_object(request, staff_id)
        role = str(request.data.get("role", "")).strip()
        management.add_role(
            membership=profile.membership, role=role, actor=request.user, request=request
        )
        profile.membership.refresh_from_db()
        return Response(_serialize_staff(self.get_object(request, staff_id), full_mobile=True))


class StaffRoleDeleteView(StaffDetailView):
    def delete(self, request: Request, staff_id: int, role: str) -> Response:
        profile = self.get_object(request, staff_id)
        management.remove_role(
            membership=profile.membership, role=role, actor=request.user, request=request
        )
        return Response(_serialize_staff(self.get_object(request, staff_id), full_mobile=True))


class StaffSuspendView(StaffDetailView):
    def post(self, request: Request, staff_id: int) -> Response:
        profile = self.get_object(request, staff_id)
        management.suspend(membership=profile.membership, actor=request.user, request=request)
        return Response(_serialize_staff(self.get_object(request, staff_id), full_mobile=True))


class StaffActivateView(StaffDetailView):
    def post(self, request: Request, staff_id: int) -> Response:
        profile = self.get_object(request, staff_id)
        management.reactivate(
            membership=profile.membership, actor=request.user, request=request
        )
        return Response(_serialize_staff(self.get_object(request, staff_id), full_mobile=True))


class StaffReinviteView(StaffDetailView):
    def post(self, request: Request, staff_id: int) -> Response:
        profile = self.get_object(request, staff_id)
        management.reinvite(membership=profile.membership, actor=request.user, request=request)
        return Response(_serialize_staff(self.get_object(request, staff_id), full_mobile=True))


# ---------- الاستيراد ----------


def _serialize_job(job: StaffImportJob) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "original_filename": job.original_filename,
        "headers": job.headers,
        "column_mapping": job.column_mapping,
        "suggested_mapping": job.summary.get("suggested_mapping"),
        "total_rows": job.total_rows,
        "valid_rows": job.valid_rows,
        "invalid_rows": job.invalid_rows,
        "duplicate_rows": job.duplicate_rows,
        "new_user_rows": job.new_user_rows,
        "existing_user_rows": job.existing_user_rows,
        "summary": {k: v for k, v in job.summary.items() if k != "suggested_mapping"},
        "error_code": job.error_code,
        "created_at": job.created_at.isoformat(),
    }


class StaffImportUploadView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    def get(self, request: Request) -> Response:
        jobs = StaffImportJob.objects.filter(school=request.school).order_by("-id")[:20]
        return Response([_serialize_job(j) for j in jobs])

    def post(self, request: Request) -> Response:
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ApiError("VALIDATION_ERROR", "أرفق ملف Excel في الحقل file.")
        validate_upload(
            uploaded,
            unsupported_code="STAFF_IMPORT_INVALID_FILE",
            invalid_code="STAFF_IMPORT_INVALID_FILE",
        )
        headers = read_headers(uploaded)
        suggested = mapping_service.suggest_mapping(headers)
        job = StaffImportJob.objects.create(
            school=request.school,
            uploaded_by=request.user,
            original_filename=uploaded.name[:255],
            file=uploaded,
            headers=headers,
            summary={"suggested_mapping": suggested},
        )
        record_event(
            AuditAction.STAFF_IMPORT_UPLOADED,
            request=request, actor=request.user, school=request.school,
            target_type="StaffImportJob", target_id=job.id,
            metadata={"filename": job.original_filename},
        )
        return Response(_serialize_job(job), status=http_status.HTTP_201_CREATED)


class StaffImportJobView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    def get(self, request: Request, job_id: int) -> Response:
        job = get_object_or_404(StaffImportJob, id=job_id, school=request.school)
        return Response(_serialize_job(job))


class StaffImportProcessView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    def post(self, request: Request, job_id: int) -> Response:
        job = get_object_or_404(StaffImportJob, id=job_id, school=request.school)
        if job.status not in (
            StaffImportStatus.UPLOADED,
            StaffImportStatus.READY_FOR_REVIEW,
            StaffImportStatus.FAILED,
        ):
            raise ApiError("IMPORT_ALREADY_RUNNING", "الاستيراد قيد التنفيذ حالياً.", 409)
        mapping = request.data.get("mapping") or job.summary.get("suggested_mapping") or {}
        mapping = {k: v for k, v in mapping.items() if v is not None}
        mapping_service.validate_mapping(mapping, headers_count=len(job.headers))
        job.column_mapping = mapping
        job.status = StaffImportStatus.PROCESSING
        job.error_code = ""
        job.save(update_fields=["column_mapping", "status", "error_code", "updated_at"])
        process_staff_import_job.delay(job.id)
        return Response(_serialize_job(job), status=http_status.HTTP_202_ACCEPTED)


class StaffImportPreviewView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    def get(self, request: Request, job_id: int) -> Response:
        job = get_object_or_404(StaffImportJob, id=job_id, school=request.school)
        if job.status != StaffImportStatus.READY_FOR_REVIEW:
            raise ApiError("IMPORT_NOT_READY", "المعاينة غير جاهزة بعد.", status_code=409)
        rows = job.rows.all()
        category = request.query_params.get("category", "").strip()
        if category:
            rows = rows.filter(status=category)
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(rows, request)
        return paginator.get_paginated_response(
            [
                {
                    "row_number": r.row_number,
                    "status": r.status,
                    "data": r.data,  # الجوال فيه mobile_masked فقط
                    "error_codes": r.error_codes,
                    "error_message": r.error_message,
                }
                for r in page
            ]
        )


class StaffImportCommitView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    def post(self, request: Request, job_id: int) -> Response:
        job = get_object_or_404(StaffImportJob, id=job_id, school=request.school)
        job, credentials = commit_service.commit_import(
            job_id=job.id, actor=request.user, request=request
        )
        payload = _serialize_job(job)
        # كلمات المرور المؤقتة: في هذه الاستجابة فقط — تظهر مرة واحدة ولا تخزن
        payload["new_credentials"] = credentials
        return Response(payload)


class StaffImportCancelView(SchoolScopedAPIView):
    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    def post(self, request: Request, job_id: int) -> Response:
        job = get_object_or_404(StaffImportJob, id=job_id, school=request.school)
        if job.status in (StaffImportStatus.COMPLETED, StaffImportStatus.IMPORTING):
            raise ApiError(
                "STAFF_IMPORT_ALREADY_COMMITTED", "لا يمكن إلغاء استيراد معتمد.", 409
            )
        job.status = StaffImportStatus.CANCELLED
        job.save(update_fields=["status", "updated_at"])
        job.rows.all().delete()
        if job.file:
            job.file.delete(save=False)
            job.file = None
            job.save(update_fields=["file"])
        return Response(_serialize_job(job))

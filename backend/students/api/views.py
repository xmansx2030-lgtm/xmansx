"""واجهات الطلاب والاستيراد والملف القرائي — كلها مقيدة بـ request.school (أجنبي → 404).

الصلاحيات: القراءة MANAGER/VICE/COUNSELOR — الاستيراد MANAGER فقط —
TEACHER لا يملك قائمة طلاب عامة في هذه المرحلة (تأتي مع الحضور).
"""

from django.shortcuts import get_object_or_404
from django.utils import timezone as dj_timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework.request import Request
from rest_framework.response import Response

from academics.models import AcademicYear, AcademicYearStatus
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from common.pagination import DefaultPagination
from memberships.api_base import SETTINGS_WRITE_ROLES, SchoolScopedAPIView
from students.api.profile_serializers import (
    AttendanceChangeSerializer,
    AttendanceDaySerializer,
    AttendancePeriodSerializer,
    AttendanceProfileSerializer,
    MorningAttendanceHistorySerializer,
)
from students.models import (
    Grade,
    ImportJobStatus,
    Section,
    StudentImportJob,
)
from students.services import attendance_profile as attendance_profile_service
from students.services import morning_profile as morning_profile_service
from students.services.imports import commit as commit_service
from students.services.imports import mapping as mapping_service
from students.services.imports import parser as parser_service
from students.services.queries import students_queryset
from students.tasks import process_import_job


def _active_year(school) -> AcademicYear | None:
    return AcademicYear.objects.filter(
        school=school, status=AcademicYearStatus.ACTIVE
    ).first()


def _serialize_student(student) -> dict:
    enrollment = student.active_enrollments[0] if student.active_enrollments else None
    return {
        "id": student.id,
        "full_name": student.full_name,
        "national_id_masked": student.national_id_masked,  # لا رقم كامل في القوائم
        "student_number": student.student_number,
        "status": student.status,
        "guardian_name": student.guardian_name,
        "grade": (
            {"id": enrollment.grade.id, "name": enrollment.grade.name} if enrollment else None
        ),
        "section": (
            {"id": enrollment.section.id, "name": enrollment.section.name}
            if enrollment
            else None
        ),
    }


class StudentListView(SchoolScopedAPIView):
    def get(self, request: Request) -> Response:
        queryset = students_queryset(
            school=request.school,
            academic_year=_active_year(request.school),
            search=request.query_params.get("search", "").strip(),
            national_id=request.query_params.get("national_id", "").strip(),
            grade_id=request.query_params.get("grade") or None,
            section_id=request.query_params.get("section") or None,
            status=request.query_params.get("status", "").strip(),
        )
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response([_serialize_student(s) for s in page])


class StudentSearchView(StudentListView):
    """البحث الرئيسي للملف — النشطون افتراضياً، والهوية exact عبر HMAC."""

    read_roles = ("SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR")

    def get(self, request: Request) -> Response:
        query = request.query_params.copy()
        if not query.get("status"):
            query["status"] = "ACTIVE"
        request._request.GET = query
        return super().get(request)


class StudentDetailView(SchoolScopedAPIView):
    def get(self, request: Request, student_id: int) -> Response:
        queryset = students_queryset(
            school=request.school, academic_year=_active_year(request.school)
        )
        student = get_object_or_404(queryset, id=student_id)
        return Response(_serialize_student(student))


class GradeListView(SchoolScopedAPIView):
    def get(self, request: Request) -> Response:
        grades = Grade.objects.filter(school=request.school, is_active=True)
        return Response(
            [{"id": g.id, "name": g.name, "code": g.code, "sequence": g.sequence} for g in grades]
        )


class SectionListView(SchoolScopedAPIView):
    def get(self, request: Request) -> Response:
        sections = Section.objects.filter(
            school=request.school, is_active=True
        ).select_related("grade")
        grade_id = request.query_params.get("grade")
        if grade_id:
            sections = sections.filter(grade_id=grade_id)
        return Response(
            [
                {"id": s.id, "name": s.name, "code": s.code,
                 "grade": {"id": s.grade.id, "name": s.grade.name}}
                for s in sections
            ]
        )


def _serialize_job(job: StudentImportJob) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "original_filename": job.original_filename,
        "headers": job.headers,
        "column_mapping": job.column_mapping,
        "suggested_mapping": job.summary.get("suggested_mapping"),
        "academic_year": {"id": job.academic_year_id},
        "total_rows": job.total_rows,
        "valid_rows": job.valid_rows,
        "invalid_rows": job.invalid_rows,
        "duplicate_rows": job.duplicate_rows,
        "summary": {k: v for k, v in job.summary.items() if k != "suggested_mapping"},
        "error_code": job.error_code,
        "created_at": job.created_at.isoformat(),
    }


class ImportUploadView(SchoolScopedAPIView):
    """رفع الملف (MANAGER فقط) — فحوص أمنية فورية + اقتراح mapping من الرؤوس."""

    read_roles = SETTINGS_WRITE_ROLES  # حتى GET القائمة للمدير فقط
    write_roles = SETTINGS_WRITE_ROLES

    def get(self, request: Request) -> Response:
        jobs = StudentImportJob.objects.filter(school=request.school).order_by("-id")[:20]
        return Response([_serialize_job(j) for j in jobs])

    def post(self, request: Request) -> Response:
        year = _active_year(request.school)
        if year is None:
            raise ApiError(
                "ACTIVE_ACADEMIC_YEAR_REQUIRED",
                "لم يتم العثور على عام دراسي نشط لهذه المدرسة.",
                status_code=409,
            )
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ApiError("VALIDATION_ERROR", "أرفق ملف Excel في الحقل file.")

        parser_service.validate_upload(uploaded)
        headers = parser_service.read_headers(uploaded)
        suggested = mapping_service.suggest_mapping(headers)

        job = StudentImportJob.objects.create(
            school=request.school,
            uploaded_by=request.user,
            academic_year=year,
            original_filename=uploaded.name[:255],
            file=uploaded,
            headers=headers,
            summary={"suggested_mapping": suggested},
        )
        record_event(
            AuditAction.STUDENT_IMPORT_UPLOADED,
            request=request, actor=request.user, school=request.school,
            target_type="StudentImportJob", target_id=job.id,
            metadata={"filename": job.original_filename},
        )
        return Response(_serialize_job(job), status=http_status.HTTP_201_CREATED)


class ImportJobView(SchoolScopedAPIView):
    read_roles = SETTINGS_WRITE_ROLES
    write_roles = SETTINGS_WRITE_ROLES

    def get(self, request: Request, job_id: int) -> Response:
        job = get_object_or_404(StudentImportJob, id=job_id, school=request.school)
        return Response(_serialize_job(job))


class ImportProcessView(SchoolScopedAPIView):
    """تأكيد الـ mapping وبدء المعالجة عبر Celery — 202 ثم Polling."""

    read_roles = SETTINGS_WRITE_ROLES
    write_roles = SETTINGS_WRITE_ROLES

    def post(self, request: Request, job_id: int) -> Response:
        job = get_object_or_404(StudentImportJob, id=job_id, school=request.school)
        if job.status not in (ImportJobStatus.UPLOADED, ImportJobStatus.READY_FOR_REVIEW,
                              ImportJobStatus.FAILED):
            raise ApiError("IMPORT_ALREADY_RUNNING", "الاستيراد قيد التنفيذ حالياً.", 409)

        mapping = request.data.get("mapping") or job.summary.get("suggested_mapping") or {}
        mapping = {k: v for k, v in mapping.items() if v is not None}
        mapping_service.validate_mapping(mapping, headers_count=len(job.headers))

        job.column_mapping = mapping
        job.status = ImportJobStatus.PROCESSING
        job.error_code = ""
        job.save(update_fields=["column_mapping", "status", "error_code", "updated_at"])
        process_import_job.delay(job.id)
        return Response(_serialize_job(job), status=http_status.HTTP_202_ACCEPTED)


class ImportPreviewView(SchoolScopedAPIView):
    read_roles = SETTINGS_WRITE_ROLES
    write_roles = SETTINGS_WRITE_ROLES

    def get(self, request: Request, job_id: int) -> Response:
        job = get_object_or_404(StudentImportJob, id=job_id, school=request.school)
        if job.status != ImportJobStatus.READY_FOR_REVIEW:
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
                    "data": r.data,  # الهوية فيه مقنعة فقط
                    "error_codes": r.error_codes,
                    "error_message": r.error_message,
                }
                for r in page
            ]
        )


class ImportCommitView(SchoolScopedAPIView):
    read_roles = SETTINGS_WRITE_ROLES
    write_roles = SETTINGS_WRITE_ROLES

    def post(self, request: Request, job_id: int) -> Response:
        job = get_object_or_404(StudentImportJob, id=job_id, school=request.school)
        job = commit_service.commit_import(job_id=job.id, actor=request.user, request=request)
        return Response(_serialize_job(job))


class ImportCancelView(SchoolScopedAPIView):
    read_roles = SETTINGS_WRITE_ROLES
    write_roles = SETTINGS_WRITE_ROLES

    def post(self, request: Request, job_id: int) -> Response:
        job = get_object_or_404(StudentImportJob, id=job_id, school=request.school)
        if job.status in (ImportJobStatus.COMPLETED, ImportJobStatus.IMPORTING):
            raise ApiError("IMPORT_ALREADY_COMMITTED", "لا يمكن إلغاء استيراد معتمد.", 409)
        job.status = ImportJobStatus.CANCELLED
        job.save(update_fields=["status", "updated_at"])
        job.rows.all().delete()
        if job.file:
            job.file.delete(save=False)
            job.file = None
            job.save(update_fields=["file"])
        return Response(_serialize_job(job))


PROFILE_READ_ROLES = ("SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR")
PROFILE_ADMIN_ROLES = ("SCHOOL_MANAGER", "VICE_PRINCIPAL")


def _profile_dates(request: Request):
    from datetime import date as date_cls

    def parse(name):
        value = request.query_params.get(name)
        if not value:
            return None
        try:
            return date_cls.fromisoformat(value)
        except ValueError:
            raise ApiError(
                "INVALID_ATTENDANCE_DATE_RANGE",
                "صيغة التاريخ غير صحيحة (YYYY-MM-DD).",
            ) from None

    from_date = parse("from_date")
    to_date = parse("to_date")
    if from_date is None or to_date is None:
        year = _active_year(request.school)
        if year is not None:
            from_date = from_date or year.start_date
            to_date = to_date or year.end_date
        else:
            today = dj_timezone.localdate()
            from_date = from_date or today
            to_date = to_date or today
    try:
        attendance_profile_service.validate_profile_range(from_date, to_date)
    except ValueError as exc:
        if str(exc) == "ATTENDANCE_PROFILE_RANGE_TOO_LARGE":
            raise ApiError(
                "ATTENDANCE_PROFILE_RANGE_TOO_LARGE",
                "الفترة المطلوبة أكبر من عام دراسي واحد.",
            ) from None
        raise ApiError(
            "INVALID_ATTENDANCE_DATE_RANGE", "الفترة المطلوبة غير صحيحة."
        ) from None
    return from_date, to_date


def _profile_student(request: Request, student_id: int):
    return get_object_or_404(
        attendance_profile_service.profile_student_queryset(
            school=request.school, student_id=student_id
        ),
        id=student_id,
    )


class StudentAttendanceProfileView(SchoolScopedAPIView):
    read_roles = PROFILE_READ_ROLES
    write_roles = PROFILE_ADMIN_ROLES

    @extend_schema(responses=AttendanceProfileSerializer)
    def get(self, request: Request, student_id: int) -> Response:
        student = _profile_student(request, student_id)
        from_date, to_date = _profile_dates(request)
        return Response({
            "student": attendance_profile_service.serialize_student_header(student),
            "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
            "attendance": attendance_profile_service.get_profile_summary(
                school=request.school, student=student, from_date=from_date, to_date=to_date
            ),
            "morning_attendance": morning_profile_service.get_morning_profile_summary(
                school=request.school, student=student, from_date=from_date, to_date=to_date
            ),
        })


class StudentAttendanceDaysView(SchoolScopedAPIView):
    read_roles = PROFILE_READ_ROLES
    write_roles = PROFILE_ADMIN_ROLES

    @extend_schema(responses=AttendanceDaySerializer(many=True))
    def get(self, request: Request, student_id: int) -> Response:
        student = _profile_student(request, student_id)
        from_date, to_date = _profile_dates(request)
        queryset = attendance_profile_service.get_daily_history(
            school=request.school, student=student, from_date=from_date, to_date=to_date
        )
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response([
            {
                "date": row.attendance_date,
                "absence_status": row.absence_status,
                "absence_status_label": attendance_profile_service.ABSENCE_LABELS[
                    row.absence_status
                ],
                "section": {
                    "id": row.section_id,
                    "name": row.section.name,
                    "grade_name": row.section.grade.name,
                },
                "absent_periods": row.absent_periods,
                "excused_absent_periods": row.excused_absent_periods,
                "unexcused_absent_periods": row.unexcused_absent_periods,
                "late_periods": row.late_periods,
                "total_late_minutes": row.total_late_minutes,
            }
            for row in page
        ])


class StudentMorningAttendanceView(SchoolScopedAPIView):
    read_roles = PROFILE_READ_ROLES
    write_roles = PROFILE_ADMIN_ROLES

    @extend_schema(responses=MorningAttendanceHistorySerializer(many=True))
    def get(self, request: Request, student_id: int) -> Response:
        student = _profile_student(request, student_id)
        from_date, to_date = _profile_dates(request)
        arrivals = morning_profile_service.get_morning_profile_history(
            school=request.school, student=student, from_date=from_date, to_date=to_date
        )
        return Response(morning_profile_service.serialize_morning_history(
            school=request.school, arrivals=arrivals
        ))


class StudentAttendanceDayDetailView(SchoolScopedAPIView):
    read_roles = PROFILE_READ_ROLES
    write_roles = PROFILE_ADMIN_ROLES

    @extend_schema(responses=AttendanceDaySerializer)
    def get(self, request: Request, student_id: int, attendance_date: str) -> Response:
        from datetime import date as date_cls

        student = _profile_student(request, student_id)
        try:
            target = date_cls.fromisoformat(attendance_date)
        except ValueError:
            raise ApiError(
                "INVALID_ATTENDANCE_DATE_RANGE",
                "صيغة التاريخ غير صحيحة (YYYY-MM-DD).",
            ) from None
        return Response(
            attendance_profile_service.get_day_detail(
                school=request.school, student=student, attendance_date=target
            )
        )


def _page_size(request: Request) -> int:
    value = request.query_params.get("page_size", "25")
    try:
        page_size = int(value)
    except ValueError:
        raise ApiError("VALIDATION_ERROR", "حجم الصفحة غير صحيح.") from None
    if page_size not in (25, 50, 100):
        raise ApiError("VALIDATION_ERROR", "حجم الصفحة يجب أن يكون 25 أو 50 أو 100.")
    return page_size


class _StudentAttendanceMarksView(SchoolScopedAPIView):
    read_roles = PROFILE_READ_ROLES
    write_roles = PROFILE_ADMIN_ROLES
    mark_status = None

    @extend_schema(responses=AttendancePeriodSerializer(many=True))
    def get(self, request: Request, student_id: int) -> Response:
        student = _profile_student(request, student_id)
        from_date, to_date = _profile_dates(request)
        paginator = DefaultPagination()
        paginator.page_size = _page_size(request)
        page = paginator.paginate_queryset(
            attendance_profile_service.get_period_marks(
                school=request.school,
                student=student,
                from_date=from_date,
                to_date=to_date,
                status=self.mark_status,
            ),
            request,
        )
        return paginator.get_paginated_response([
            {
                "date": mark.session.attendance_date,
                "sequence": mark.session.period_sequence,
                "period": mark.session.bell_period_snapshot,
                "section": {
                    "name": mark.session.section.name,
                    "grade_name": mark.session.section.grade.name,
                },
                "arrival_time": mark.arrival_time.strftime("%H:%M") if mark.arrival_time else None,
                "late_minutes": mark.late_minutes,
            }
            for mark in page
        ])


class StudentAttendanceAbsencesView(_StudentAttendanceMarksView):
    mark_status = "ABSENT"


class StudentAttendanceLatesView(_StudentAttendanceMarksView):
    mark_status = "LATE"


class StudentAttendanceChangesView(SchoolScopedAPIView):
    read_roles = PROFILE_ADMIN_ROLES
    write_roles = PROFILE_ADMIN_ROLES

    @extend_schema(responses=AttendanceChangeSerializer(many=True))
    def get(self, request: Request, student_id: int) -> Response:
        student = _profile_student(request, student_id)
        from_date, to_date = _profile_dates(request)
        paginator = DefaultPagination()
        paginator.page_size = _page_size(request)
        page = paginator.paginate_queryset(
            attendance_profile_service.get_attendance_changes(
                school=request.school,
                student=student,
                from_date=from_date,
                to_date=to_date,
            ),
            request,
        )
        return paginator.get_paginated_response([
            {
                "date": change.session.attendance_date,
                "sequence": change.session.period_sequence,
                "period": change.session.bell_period_snapshot,
                "previous_status": change.previous_status,
                "new_status": change.new_status,
                "previous_status_label": attendance_profile_service.MARK_LABELS.get(
                    change.previous_status, change.previous_status
                ),
                "new_status_label": attendance_profile_service.MARK_LABELS.get(
                    change.new_status, change.new_status
                ),
                "previous_late_minutes": change.previous_late_minutes,
                "new_late_minutes": change.new_late_minutes,
                "reason": change.reason or None,
                "actor": (
                    change.actor_membership.staff_profile.display_name
                    if getattr(change.actor_membership, "staff_profile", None)
                    else change.actor_membership.user.display_name
                ),
                "changed_at": change.changed_at,
            }
            for change in page
        ])

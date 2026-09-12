"""واجهات الطلاب والاستيراد والملف القرائي — كلها مقيدة بـ request.school (أجنبي → 404).

الصلاحيات: القراءة MANAGER/VICE/COUNSELOR — الاستيراد MANAGER فقط —
TEACHER لا يملك قائمة طلاب عامة في هذه المرحلة (تأتي مع الحضور).
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone as dj_timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework import status as http_status
from rest_framework.request import Request
from rest_framework.response import Response

from academics.models import AcademicYear, AcademicYearStatus
from accounts.mobile import normalize_mobile
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from common.pagination import DefaultPagination
from common.security.identifiers import normalize_national_id
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
    StudentImportRow,
)
from students.services import attendance_profile as attendance_profile_service
from students.services import manual as manual_service
from students.services import morning_profile as morning_profile_service
from students.services import structure as structure_service
from students.services.imports import mapping as mapping_service
from students.services.imports import parser as parser_service
from students.services.imports import review as review_service
from students.services.queries import students_queryset
from students.tasks import commit_student_import_job, process_import_job


def _active_year(school) -> AcademicYear | None:
    return AcademicYear.objects.filter(school=school, status=AcademicYearStatus.ACTIVE).first()


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
            {"id": enrollment.section.id, "name": enrollment.section.name} if enrollment else None
        ),
    }


class StudentCreateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=200)
    national_id = serializers.CharField(max_length=30, write_only=True)
    student_number = serializers.CharField(max_length=30, required=False, allow_blank=True)
    guardian_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    guardian_mobile = serializers.CharField(max_length=30, required=False, allow_blank=True)
    section_id = serializers.IntegerField(min_value=1)

    def validate_full_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("أدخل اسم الطالب كاملًا.")
        return value

    def validate_national_id(self, value):
        try:
            return normalize_national_id(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from exc

    def validate_guardian_mobile(self, value):
        if not value.strip():
            return ""
        try:
            return normalize_mobile(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from exc

    def validate_student_number(self, value):
        return value.strip()

    def validate_guardian_name(self, value):
        return value.strip()


class StudentPatchSerializer(serializers.Serializer):
    """تصحيح يدوي؛ رقم الهوية اختياري ولا يعاد كشف القيمة الحالية."""

    full_name = serializers.CharField(max_length=200, required=False)
    national_id = serializers.CharField(max_length=30, required=False, write_only=True)
    student_number = serializers.CharField(
        max_length=30, required=False, allow_blank=True
    )
    guardian_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True
    )
    guardian_mobile = serializers.CharField(
        max_length=30, required=False, allow_blank=True
    )
    section_id = serializers.IntegerField(min_value=1, required=False)

    def validate_full_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("أدخل اسم الطالب كاملًا.")
        return value

    def validate_national_id(self, value):
        try:
            return normalize_national_id(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from exc

    def validate_guardian_mobile(self, value):
        if not value.strip():
            return ""
        try:
            return normalize_mobile(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from exc

    def validate_student_number(self, value):
        return value.strip()

    def validate_guardian_name(self, value):
        return value.strip()


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

    def post(self, request: Request) -> Response:
        serializer = StudentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        year = _active_year(request.school)
        if year is None:
            raise ApiError(
                "ACTIVE_ACADEMIC_YEAR_REQUIRED",
                "يجب تفعيل عام دراسي قبل إضافة طالب.",
                status_code=409,
            )
        section = get_object_or_404(
            Section.objects.select_related("grade"),
            id=serializer.validated_data["section_id"],
            school=request.school,
            is_active=True,
            grade__is_active=True,
        )
        student = manual_service.create_student(
            school=request.school,
            academic_year=year,
            section=section,
            data=serializer.validated_data,
            actor=request.user,
            request=request,
        )
        created = students_queryset(school=request.school, academic_year=year).get(id=student.id)
        return Response(_serialize_student(created), status=http_status.HTTP_201_CREATED)


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
    write_roles = SETTINGS_WRITE_ROLES

    def get(self, request: Request, student_id: int) -> Response:
        queryset = students_queryset(
            school=request.school, academic_year=_active_year(request.school)
        )
        student = get_object_or_404(queryset, id=student_id)
        return Response(_serialize_student(student))

    def patch(self, request: Request, student_id: int) -> Response:
        serializer = StudentPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        year = _active_year(request.school)
        # 404 معزول بدل تسريب وجود طالب من مدرسة أخرى أو تحويله إلى خطأ 500.
        get_object_or_404(
            students_queryset(school=request.school, academic_year=year),
            id=student_id,
        )
        section = None
        if "section_id" in data:
            if year is None:
                raise ApiError(
                    "ACTIVE_ACADEMIC_YEAR_REQUIRED",
                    "يجب تفعيل عام دراسي قبل تعديل فصل الطالب.",
                    status_code=409,
                )
            section = get_object_or_404(
                Section.objects.select_related("grade"),
                id=data.pop("section_id"),
                school=request.school,
                is_active=True,
                grade__is_active=True,
            )
        student = manual_service.update_student(
            school=request.school,
            student_id=student_id,
            academic_year=year,
            section=section,
            data=data,
            actor=request.user,
            request=request,
        )
        updated = students_queryset(
            school=request.school, academic_year=year
        ).get(id=student.id)
        return Response(_serialize_student(updated))


def _include_inactive(request: Request) -> bool:
    return str(request.query_params.get("include_inactive", "")).lower() in {"1", "true"}


def _grade_payload(grade: Grade) -> dict:
    return {
        "id": grade.id,
        "name": grade.name,
        "code": grade.code,
        "sequence": grade.sequence,
        "is_active": grade.is_active,
    }


def _section_payload(section: Section) -> dict:
    return {
        "id": section.id,
        "name": section.name,
        "code": section.code,
        "is_active": section.is_active,
        "grade": {
            "id": section.grade.id,
            "name": section.grade.name,
            "is_active": section.grade.is_active,
        },
    }


class GradeListView(SchoolScopedAPIView):
    def get(self, request: Request) -> Response:
        grades = Grade.objects.filter(school=request.school)
        if not _include_inactive(request):
            grades = grades.filter(is_active=True)
        return Response([_grade_payload(grade) for grade in grades])

    def post(self, request: Request) -> Response:
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["name"] = serializers.CharField(max_length=100, trim_whitespace=True)
        serializer.fields["code"] = serializers.CharField(max_length=50, trim_whitespace=True)
        serializer.fields["sequence"] = serializers.IntegerField(
            min_value=0, max_value=32767, default=0
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if Grade.objects.filter(school=request.school, code__iexact=data["code"]).exists():
            raise ApiError("GRADE_CODE_ALREADY_EXISTS", "رمز الصف مستخدم مسبقًا.", status_code=409)
        try:
            grade = Grade.objects.create(school=request.school, **data)
        except IntegrityError as exc:
            raise ApiError(
                "GRADE_CODE_ALREADY_EXISTS", "رمز الصف مستخدم مسبقًا.", status_code=409
            ) from exc
        record_event(
            AuditAction.GRADE_CREATED,
            request=request,
            actor=request.user,
            school=request.school,
            target_type="Grade",
            target_id=grade.id,
            metadata={"sequence": grade.sequence},
        )
        return Response(_grade_payload(grade), status=http_status.HTTP_201_CREATED)


class GradeDetailView(SchoolScopedAPIView):
    http_method_names = ["patch", "delete", "options"]

    def get_object(self, request: Request, grade_id: int) -> Grade:
        return get_object_or_404(Grade, school=request.school, id=grade_id)

    def patch(self, request: Request, grade_id: int) -> Response:
        grade = self.get_object(request, grade_id)
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["name"] = serializers.CharField(
            max_length=100, trim_whitespace=True, required=False
        )
        serializer.fields["code"] = serializers.CharField(
            max_length=50, trim_whitespace=True, required=False
        )
        serializer.fields["sequence"] = serializers.IntegerField(
            min_value=0, max_value=32767, required=False
        )
        serializer.fields["is_active"] = serializers.BooleanField(required=False)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data:
            raise ApiError("VALIDATION_ERROR", "أرسل حقلًا واحدًا على الأقل للتعديل.")
        grade = structure_service.update_grade(
            grade=grade,
            data=serializer.validated_data,
            actor=request.user,
            request=request,
        )
        return Response(_grade_payload(grade))

    def delete(self, request: Request, grade_id: int) -> Response:
        structure_service.delete_grade(
            grade=self.get_object(request, grade_id), actor=request.user, request=request
        )
        return Response(status=http_status.HTTP_204_NO_CONTENT)


class SectionListView(SchoolScopedAPIView):
    def get(self, request: Request) -> Response:
        sections = Section.objects.filter(school=request.school).select_related("grade")
        if not _include_inactive(request):
            sections = sections.filter(is_active=True, grade__is_active=True)
        grade_id = request.query_params.get("grade")
        if grade_id:
            sections = sections.filter(grade_id=grade_id)
        return Response([_section_payload(section) for section in sections])

    def post(self, request: Request) -> Response:
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["grade_id"] = serializers.IntegerField(min_value=1)
        serializer.fields["name"] = serializers.CharField(max_length=50, trim_whitespace=True)
        serializer.fields["code"] = serializers.CharField(max_length=50, trim_whitespace=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        grade = get_object_or_404(Grade, school=request.school, id=data["grade_id"], is_active=True)
        if Section.objects.filter(
            school=request.school, grade=grade, code__iexact=data["code"]
        ).exists():
            raise ApiError(
                "SECTION_CODE_ALREADY_EXISTS", "رمز الفصل مستخدم مسبقًا داخل الصف.", status_code=409
            )
        try:
            section = Section.objects.create(
                school=request.school,
                grade=grade,
                name=data["name"],
                code=data["code"],
            )
        except IntegrityError as exc:
            raise ApiError(
                "SECTION_CODE_ALREADY_EXISTS",
                "رمز الفصل مستخدم مسبقًا داخل الصف.",
                status_code=409,
            ) from exc
        record_event(
            AuditAction.SECTION_CREATED,
            request=request,
            actor=request.user,
            school=request.school,
            target_type="Section",
            target_id=section.id,
            metadata={"grade_id": grade.id},
        )
        return Response(_section_payload(section), status=http_status.HTTP_201_CREATED)


class SectionDetailView(SchoolScopedAPIView):
    http_method_names = ["patch", "delete", "options"]

    def get_object(self, request: Request, section_id: int) -> Section:
        return get_object_or_404(
            Section.objects.select_related("grade"), school=request.school, id=section_id
        )

    def patch(self, request: Request, section_id: int) -> Response:
        section = self.get_object(request, section_id)
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["grade_id"] = serializers.IntegerField(min_value=1, required=False)
        serializer.fields["name"] = serializers.CharField(
            max_length=50, trim_whitespace=True, required=False
        )
        serializer.fields["code"] = serializers.CharField(
            max_length=50, trim_whitespace=True, required=False
        )
        serializer.fields["is_active"] = serializers.BooleanField(required=False)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if not data:
            raise ApiError("VALIDATION_ERROR", "أرسل حقلًا واحدًا على الأقل للتعديل.")
        if "grade_id" in data:
            data["grade"] = get_object_or_404(
                Grade, school=request.school, id=data.pop("grade_id")
            )
        section = structure_service.update_section(
            section=section, data=data, actor=request.user, request=request
        )
        return Response(_section_payload(section))

    def delete(self, request: Request, section_id: int) -> Response:
        structure_service.delete_section(
            section=self.get_object(request, section_id), actor=request.user, request=request
        )
        return Response(status=http_status.HTTP_204_NO_CONTENT)


IMPORT_ERROR_MESSAGES = {
    "ACTIVE_ACADEMIC_YEAR_REQUIRED": (
        "تغير العام الدراسي النشط منذ رفع الملف. أعد الاستيراد من جديد."
    ),
    "IMPORT_COMMIT_FAILED": "تعذر تثبيت بيانات الاستيراد. حاول مرة أخرى أو تواصل مع الدعم.",
    "IMPORT_PREVIEW_STALE": (
        "تغيرت بيانات الطلاب منذ إنشاء المعاينة. راجع المعاينة المحدثة ثم أعد الاعتماد."
    ),
    "STUDENT_LIMIT_EXCEEDED": "تجاوز عدد الطلاب حد الباقة. يرجى ترقية الباقة.",
    "IMPORT_ROWS_REQUIRE_REVIEW": (
        "عالج جميع الصفوف ذات الأخطاء أو التكرارات قبل اعتماد الاستيراد."
    ),
}


class ImportRowCorrectionSerializer(serializers.Serializer):
    national_id = serializers.CharField(max_length=40, required=False, trim_whitespace=True)
    student_number = serializers.CharField(
        max_length=30, required=False, allow_blank=True, trim_whitespace=True
    )
    full_name = serializers.CharField(max_length=200, required=False, trim_whitespace=True)
    section_id = serializers.IntegerField(min_value=1, required=False)
    section_code = serializers.CharField(max_length=50, required=False, trim_whitespace=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("أرسل تصحيحًا واحدًا على الأقل.")
        if "section_id" in attrs and "section_code" in attrs:
            raise serializers.ValidationError("اختر مصدرًا واحدًا للفصل الصحيح.")
        return attrs


def _serialize_job(job: StudentImportJob) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "original_filename": job.original_filename,
        "headers": job.headers,
        "header_row": int(job.summary.get("header_row", 1)),
        "import_format": job.summary.get("import_format", "TABULAR"),
        "source_sheet_count": int(job.summary.get("source_sheet_count", 1)),
        "detected_rows": int(job.summary.get("detected_rows", 0)),
        "column_mapping": job.column_mapping,
        "suggested_mapping": job.summary.get("suggested_mapping"),
        "academic_year": {"id": job.academic_year_id},
        "total_rows": job.total_rows,
        "valid_rows": job.valid_rows,
        "invalid_rows": job.invalid_rows,
        "duplicate_rows": job.duplicate_rows,
        "summary": {
            k: v
            for k, v in job.summary.items()
            if k
            not in (
                "suggested_mapping",
                "header_row",
                "import_format",
                "source_sheet_count",
                "detected_rows",
            )
        },
        "error_code": job.error_code,
        "error_message": IMPORT_ERROR_MESSAGES.get(job.error_code, ""),
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
        analysis = parser_service.analyze_import(uploaded)
        headers = analysis["headers"]
        suggested = mapping_service.suggest_mapping(headers)
        analysis_summary = {key: value for key, value in analysis.items() if key != "headers"}

        job = StudentImportJob.objects.create(
            school=request.school,
            uploaded_by=request.user,
            academic_year=year,
            original_filename=uploaded.name[:255],
            file=uploaded,
            headers=headers,
            summary={"suggested_mapping": suggested, **analysis_summary},
        )
        record_event(
            AuditAction.STUDENT_IMPORT_UPLOADED,
            request=request,
            actor=request.user,
            school=request.school,
            target_type="StudentImportJob",
            target_id=job.id,
            metadata={
                "filename": job.original_filename,
                "import_format": analysis["import_format"],
                "source_sheet_count": analysis["source_sheet_count"],
                "detected_rows": analysis["detected_rows"],
            },
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
        if job.status not in (
            ImportJobStatus.UPLOADED,
            ImportJobStatus.READY_FOR_REVIEW,
            ImportJobStatus.FAILED,
        ):
            raise ApiError("IMPORT_ALREADY_RUNNING", "الاستيراد قيد التنفيذ حالياً.", 409)

        mapping = request.data.get("mapping") or job.summary.get("suggested_mapping") or {}
        mapping = {k: v for k, v in mapping.items() if v is not None}
        mapping_service.validate_mapping(mapping, headers_count=len(job.headers))

        job.column_mapping = mapping
        job.status = ImportJobStatus.PROCESSING
        job.error_code = ""
        try:
            # Savepoint is required because Django's test/request transaction is
            # otherwise left unusable after a unique-constraint violation.
            with transaction.atomic():
                job.save(
                    update_fields=["column_mapping", "status", "error_code", "updated_at"]
                )
        except IntegrityError as exc:
            # PostgreSQL's partial unique constraint is the final arbiter under
            # simultaneous clicks/replicas. Never turn this expected race into 500.
            if StudentImportJob.objects.filter(
                school=request.school, status=ImportJobStatus.PROCESSING
            ).exclude(id=job.id).exists():
                raise ApiError(
                    "IMPORT_ALREADY_RUNNING", "يوجد استيراد آخر قيد التنفيذ لهذه المدرسة.", 409
                ) from exc
            raise
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


class ImportRowCorrectionView(SchoolScopedAPIView):
    """تصحيح صف staging مع إعادة فحص الملف كاملًا؛ لا يعيد الهوية الخام."""

    read_roles = SETTINGS_WRITE_ROLES
    write_roles = SETTINGS_WRITE_ROLES

    def patch(self, request: Request, job_id: int, row_number: int) -> Response:
        serializer = ImportRowCorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            job = get_object_or_404(
                StudentImportJob.objects.select_for_update(),
                id=job_id,
                school=request.school,
            )
            if job.status != ImportJobStatus.READY_FOR_REVIEW:
                raise ApiError(
                    "IMPORT_NOT_READY",
                    "يمكن تصحيح الصفوف أثناء مرحلة المراجعة فقط.",
                    status_code=409,
                )
            row = get_object_or_404(
                StudentImportRow.objects.select_for_update(),
                job=job,
                row_number=row_number,
            )
            changed_fields = review_service.correct_row(
                job=job, row=row, corrections=dict(serializer.validated_data)
            )
            record_event(
                AuditAction.STUDENT_IMPORT_VALIDATED,
                request=request,
                actor=request.user,
                school=job.school,
                target_type="StudentImportRow",
                target_id=row.id,
                metadata={
                    "event": "ROW_CORRECTED",
                    "job_id": job.id,
                    "row_number": row.row_number,
                    "changed_fields": changed_fields,
                },
            )
        return Response(_serialize_job(job))


class ImportCommitView(SchoolScopedAPIView):
    read_roles = SETTINGS_WRITE_ROLES
    write_roles = SETTINGS_WRITE_ROLES

    def post(self, request: Request, job_id: int) -> Response:
        with transaction.atomic():
            job = get_object_or_404(
                StudentImportJob.objects.select_for_update(),
                id=job_id,
                school=request.school,
            )
            if job.status == ImportJobStatus.COMPLETED:
                raise ApiError(
                    "IMPORT_ALREADY_COMMITTED",
                    "تم اعتماد هذا الاستيراد مسبقاً.",
                    409,
                )
            if job.status == ImportJobStatus.IMPORTING:
                return Response(_serialize_job(job), status=http_status.HTTP_202_ACCEPTED)
            if job.status == ImportJobStatus.PROCESSING:
                raise ApiError("IMPORT_ALREADY_RUNNING", "الاستيراد قيد التنفيذ حالياً.", 409)
            if job.status != ImportJobStatus.READY_FOR_REVIEW:
                raise ApiError("IMPORT_NOT_READY", "الاستيراد غير جاهز للاعتماد.", 409)
            if job.invalid_rows or job.duplicate_rows:
                raise ApiError(
                    "IMPORT_ROWS_REQUIRE_REVIEW",
                    "عالج جميع الصفوف ذات الأخطاء أو التكرارات قبل اعتماد الاستيراد.",
                    409,
                )
            job.status = ImportJobStatus.IMPORTING
            job.error_code = ""
            job.save(update_fields=["status", "error_code", "updated_at"])
            transaction.on_commit(
                lambda: commit_student_import_job.delay(job.id, request.user.id)
            )
        return Response(_serialize_job(job), status=http_status.HTTP_202_ACCEPTED)


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
        raise ApiError("INVALID_ATTENDANCE_DATE_RANGE", "الفترة المطلوبة غير صحيحة.") from None
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
        return Response(
            {
                "student": attendance_profile_service.serialize_student_header(student),
                "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
                "attendance": attendance_profile_service.get_profile_summary(
                    school=request.school, student=student, from_date=from_date, to_date=to_date
                ),
                "morning_attendance": morning_profile_service.get_morning_profile_summary(
                    school=request.school, student=student, from_date=from_date, to_date=to_date
                ),
            }
        )


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
        return paginator.get_paginated_response(
            [
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
                }
                for row in page
            ]
        )


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
        return Response(
            morning_profile_service.serialize_morning_history(
                school=request.school, arrivals=arrivals
            )
        )


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
        return paginator.get_paginated_response(
            [
                {
                    "date": mark.session.attendance_date,
                    "sequence": mark.session.period_sequence,
                    "period": mark.session.bell_period_snapshot,
                    "section": {
                        "name": mark.session.section.name,
                        "grade_name": mark.session.section.grade.name,
                    },
                }
                for mark in page
            ]
        )


class StudentAttendanceAbsencesView(_StudentAttendanceMarksView):
    mark_status = "ABSENT"


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
        return paginator.get_paginated_response(
            [
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
                    "reason": change.reason or None,
                    "actor": (
                        change.actor_membership.staff_profile.display_name
                        if getattr(change.actor_membership, "staff_profile", None)
                        else change.actor_membership.user.display_name
                    ),
                    "changed_at": change.changed_at,
                }
                for change in page
            ]
        )

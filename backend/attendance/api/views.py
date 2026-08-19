"""واجهات الحضور — TEACHER أساسًا، والتصحيح الإداري للوكيل/المدير.

can_edit المحسوب هنا للواجهة فقط — الإنفاذ الحقيقي في الخدمة.
"""

from django.shortcuts import get_object_or_404
from django.utils import timezone as dj_timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework.request import Request
from rest_framework.response import Response

from attendance.api.serializers import (
    AttendanceSectionSerializer,
    CurrentPeriodResponseSerializer,
    EditSessionSerializer,
    QrInfoSerializer,
    QrResolveSerializer,
    SessionSerializer,
    StartSessionSerializer,
    SubmitSessionSerializer,
    serialize_session,
)
from attendance.models import AttendanceSession, AttendanceSessionStatus
from attendance.services import qr as qr_service
from attendance.services import sessions as sessions_service
from attendance.services.periods import get_current_attendance_period
from common.errors import ApiError
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from schools.services.settings import get_or_create_settings
from students.models import EnrollmentStatus, Section

TEACHER_ROLES = (SchoolRole.TEACHER,)
ATTENDANCE_ROLES = (
    SchoolRole.TEACHER, SchoolRole.VICE_PRINCIPAL, SchoolRole.SCHOOL_MANAGER,
)
MANAGER_ONLY = (SchoolRole.SCHOOL_MANAGER,)


def _teacher_membership(request: Request):
    """التحضير بصفة معلم — COUNSELOR وحده لا يحضّر."""
    if SchoolRole.TEACHER not in request.school_roles:
        raise ApiError(
            "ATTENDANCE_PERMISSION_DENIED",
            "تسجيل الحضور متاح للمعلمين فقط.",
            status_code=403,
        )
    return request.membership


def _can_edit(session: AttendanceSession, request: Request) -> bool:
    if session.status != AttendanceSessionStatus.SUBMITTED:
        return True
    if set(request.school_roles) & set(sessions_service.ADMIN_CORRECTION_ROLES):
        return True
    if session.submitted_by_membership_id != request.membership.id:
        return False
    settings_obj = get_or_create_settings(school=request.school)
    elapsed = (dj_timezone.now() - session.submitted_at).total_seconds() / 60
    return elapsed <= settings_obj.attendance_edit_window_minutes


class CurrentPeriodView(SchoolScopedAPIView):
    read_roles = ATTENDANCE_ROLES
    write_roles = ATTENDANCE_ROLES

    @extend_schema(responses=CurrentPeriodResponseSerializer)
    def get(self, request: Request) -> Response:
        period, local_date = get_current_attendance_period(request.school)
        payload = None
        if period is not None:
            payload = {
                "sequence": period.sequence,
                "name": period.name,
                "start_time": period.start_time.strftime("%H:%M"),
                "end_time": period.end_time.strftime("%H:%M"),
            }
        return Response({"period": payload, "date": local_date.isoformat()})


class AttendanceSectionsView(SchoolScopedAPIView):
    """الفصول النشطة في المدرسة الحالية فقط — للمعلم (بخلاف قوائم الإدارة)."""

    read_roles = ATTENDANCE_ROLES
    write_roles = ATTENDANCE_ROLES

    @extend_schema(responses=AttendanceSectionSerializer(many=True))
    def get(self, request: Request) -> Response:
        from django.db.models import Count, Q

        sections = (
            Section.objects.filter(school=request.school, is_active=True)
            .select_related("grade")
            .annotate(
                students_count=Count(
                    "enrollments",
                    filter=Q(
                        enrollments__status=EnrollmentStatus.ACTIVE,
                        enrollments__student__status="ACTIVE",
                    ),
                )
            )
            .order_by("grade__sequence", "code")
        )
        return Response(
            [
                {
                    "id": s.id,
                    "name": s.name,
                    "grade_name": s.grade.name,
                    "students_count": s.students_count,
                }
                for s in sections
            ]
        )


class StartSessionView(SchoolScopedAPIView):
    read_roles = TEACHER_ROLES
    write_roles = TEACHER_ROLES

    @extend_schema(request=StartSessionSerializer, responses=SessionSerializer)
    def post(self, request: Request) -> Response:
        membership = _teacher_membership(request)
        serializer = StartSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        section = get_object_or_404(
            Section.objects.select_related("grade"),
            id=serializer.validated_data["section_id"],
            school=request.school,
        )
        session, roster, resumed = sessions_service.start_session(
            school=request.school, membership=membership, section=section, request=request
        )
        session = _load_session(request, session.id)
        return Response(
            serialize_session(session, roster, can_edit=_can_edit(session, request)),
            status=http_status.HTTP_200_OK if resumed else http_status.HTTP_201_CREATED,
        )


def _load_session(request: Request, session_id: int) -> AttendanceSession:
    return get_object_or_404(
        AttendanceSession.objects.select_related(
            "section__grade", "submitted_by_membership__user",
            "submitted_by_membership__staff_profile", "academic_year",
        ).prefetch_related("marks"),
        id=session_id,
        school=request.school,
    )


class SessionDetailView(SchoolScopedAPIView):
    read_roles = ATTENDANCE_ROLES
    write_roles = ATTENDANCE_ROLES

    @extend_schema(responses=SessionSerializer)
    def get(self, request: Request, session_id: int) -> Response:
        session = _load_session(request, session_id)
        roster = sessions_service.get_roster(
            school=request.school,
            section=session.section,
            academic_year=session.academic_year,
        )
        return Response(
            serialize_session(session, roster, can_edit=_can_edit(session, request))
        )

    @extend_schema(request=EditSessionSerializer, responses=SessionSerializer)
    def patch(self, request: Request, session_id: int) -> Response:
        serializer = EditSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        get_object_or_404(AttendanceSession, id=session_id, school=request.school)
        sessions_service.edit_session(
            session_id=session_id,
            school=request.school,
            membership=request.membership,
            roles=request.school_roles,
            marks=serializer.validated_data["marks"],
            reason=serializer.validated_data.get("reason", ""),
            request=request,
        )
        session = _load_session(request, session_id)
        roster = sessions_service.get_roster(
            school=request.school,
            section=session.section,
            academic_year=session.academic_year,
        )
        return Response(
            serialize_session(session, roster, can_edit=_can_edit(session, request))
        )


class SubmitSessionView(SchoolScopedAPIView):
    read_roles = TEACHER_ROLES
    write_roles = TEACHER_ROLES

    @extend_schema(request=SubmitSessionSerializer, responses=SessionSerializer)
    def post(self, request: Request, session_id: int) -> Response:
        membership = _teacher_membership(request)
        serializer = SubmitSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # التحقق من الانتماء للمدرسة قبل الخدمة (404 للأجنبي)
        get_object_or_404(AttendanceSession, id=session_id, school=request.school)
        sessions_service.submit_session(
            session_id=session_id,
            school=request.school,
            membership=membership,
            marks=serializer.validated_data["marks"],
            request=request,
        )
        session = _load_session(request, session_id)
        roster = sessions_service.get_roster(
            school=request.school,
            section=session.section,
            academic_year=session.academic_year,
        )
        return Response(
            serialize_session(session, roster, can_edit=_can_edit(session, request))
        )


class QrResolveView(SchoolScopedAPIView):
    """‏QR يحدد الفصل فقط — الصلاحية من الجلسة والعضوية والدور، لا من الرمز."""

    read_roles = TEACHER_ROLES
    write_roles = TEACHER_ROLES

    @extend_schema(request=QrResolveSerializer, responses=AttendanceSectionSerializer)
    def post(self, request: Request) -> Response:
        _teacher_membership(request)
        serializer = QrResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        section = qr_service.resolve_qr_token(
            school=request.school, token=serializer.validated_data["token"]
        )
        return Response(
            {
                "id": section.id,
                "name": section.name,
                "grade_name": section.grade.name,
                "students_count": section.enrollments.filter(
                    status=EnrollmentStatus.ACTIVE
                ).count(),
            }
        )


class SectionQrView(SchoolScopedAPIView):
    """إدارة QR الفصل — للمدير: توليد/عرض/تجديد (القديم يبطل فورًا)."""

    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    @extend_schema(responses=QrInfoSerializer)
    def get(self, request: Request, section_id: int) -> Response:
        section = get_object_or_404(
            Section.objects.select_related("grade"), id=section_id, school=request.school
        )
        token = qr_service.ensure_qr_token(
            section=section, actor=request.user, request=request
        )
        return Response(_qr_payload(section, token))

    @extend_schema(request=None, responses=QrInfoSerializer)
    def post(self, request: Request, section_id: int) -> Response:
        section = get_object_or_404(
            Section.objects.select_related("grade"), id=section_id, school=request.school
        )
        token = qr_service.rotate_qr_token(
            section=section, actor=request.user, request=request
        )
        return Response(_qr_payload(section, token))


def _qr_payload(section: Section, token: str) -> dict:
    return {
        "section_id": section.id,
        "section_name": section.name,
        "grade_name": section.grade.name,
        "token": token,
        "url_path": f"/qr/{token}",
    }

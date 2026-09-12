"""واجهات التقويم وجداول الحصص — كل الكائنات تجلب مقيدة بـ request.school (أجنبي → 404)."""

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from academics.api.serializers import (
    AcademicYearCreateInputSerializer,
    AcademicYearInputSerializer,
    AcademicYearSerializer,
    BellScheduleInputSerializer,
    BellScheduleSerializer,
    PeriodsReplaceSerializer,
    SemesterCreateInputSerializer,
    SemesterInputSerializer,
    SemesterSerializer,
    WeekDaysReplaceSerializer,
    serialize_week_day,
)
from academics.models import AcademicYear, BellSchedule, Semester
from academics.services import academic_years as years_service
from academics.services import bell_schedules as schedules_service
from academics.services import semesters as semesters_service
from academics.services import week_days as week_days_service
from memberships.api_base import SchoolScopedAPIView


def _years_queryset(request):
    return (
        AcademicYear.objects.filter(school=request.school)
        .prefetch_related("semesters")
        .order_by("-start_date")
    )


class AcademicYearListCreateView(SchoolScopedAPIView):
    def get(self, request: Request) -> Response:
        return Response(AcademicYearSerializer(_years_queryset(request), many=True).data)

    def post(self, request: Request) -> Response:
        serializer = AcademicYearCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        year = years_service.create_year(
            school=request.school,
            actor=request.user,
            request=request,
            **serializer.validated_data,
        )
        return Response(AcademicYearSerializer(year).data, status=status.HTTP_201_CREATED)


class AcademicYearDetailView(SchoolScopedAPIView):
    def patch(self, request: Request, year_id: int) -> Response:
        year = get_object_or_404(AcademicYear, id=year_id, school=request.school)
        serializer = AcademicYearInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        year = years_service.update_year(
            year=year, actor=request.user, data=serializer.validated_data, request=request
        )
        return Response(AcademicYearSerializer(year).data)


class AcademicYearActionView(SchoolScopedAPIView):
    """POST /academic-years/{id}/{action}/ — action: activate | close | archive"""

    _actions = {
        "activate": years_service.activate_year,
        "close": years_service.close_year,
        "archive": years_service.archive_year,
    }

    def post(self, request: Request, year_id: int, action: str) -> Response:
        if action not in self._actions:
            raise Http404
        year = get_object_or_404(AcademicYear, id=year_id, school=request.school)
        service = self._actions[action]
        year = service(year=year, actor=request.user, request=request)
        return Response(AcademicYearSerializer(year).data)


class SemesterListCreateView(SchoolScopedAPIView):
    def get(self, request: Request, year_id: int) -> Response:
        year = get_object_or_404(AcademicYear, id=year_id, school=request.school)
        return Response(SemesterSerializer(year.semesters.all(), many=True).data)

    def post(self, request: Request, year_id: int) -> Response:
        year = get_object_or_404(AcademicYear, id=year_id, school=request.school)
        serializer = SemesterCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        semester = semesters_service.create_semester(
            year=year, actor=request.user, request=request, **serializer.validated_data
        )
        return Response(SemesterSerializer(semester).data, status=status.HTTP_201_CREATED)


class SemesterDetailView(SchoolScopedAPIView):
    def patch(self, request: Request, semester_id: int) -> Response:
        semester = get_object_or_404(
            Semester.objects.select_related("academic_year"),
            id=semester_id,
            school=request.school,
        )
        serializer = SemesterInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        semester = semesters_service.update_semester(
            semester=semester, actor=request.user, data=serializer.validated_data, request=request
        )
        return Response(SemesterSerializer(semester).data)


class SemesterActivateView(SchoolScopedAPIView):
    def post(self, request: Request, semester_id: int) -> Response:
        semester = get_object_or_404(Semester, id=semester_id, school=request.school)
        semester = semesters_service.activate_semester(
            semester=semester, actor=request.user, request=request
        )
        return Response(SemesterSerializer(semester).data)


class BellScheduleListCreateView(SchoolScopedAPIView):
    def get(self, request: Request) -> Response:
        schedules = (
            BellSchedule.objects.filter(school=request.school)
            .exclude(status="ARCHIVED")
            .prefetch_related("periods")
            .order_by("id")
        )
        return Response(BellScheduleSerializer(schedules, many=True).data)

    def post(self, request: Request) -> Response:
        serializer = BellScheduleInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        schedule = schedules_service.create_schedule(
            school=request.school,
            actor=request.user,
            request=request,
            **serializer.validated_data,
        )
        return Response(BellScheduleSerializer(schedule).data, status=status.HTTP_201_CREATED)


class BellScheduleDetailView(SchoolScopedAPIView):
    def patch(self, request: Request, schedule_id: int) -> Response:
        schedule = get_object_or_404(BellSchedule, id=schedule_id, school=request.school)
        serializer = BellScheduleInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        schedule = schedules_service.update_schedule(
            schedule=schedule, actor=request.user, data=serializer.validated_data, request=request
        )
        return Response(BellScheduleSerializer(schedule).data)


class BellScheduleArchiveView(SchoolScopedAPIView):
    def post(self, request: Request, schedule_id: int) -> Response:
        schedule = get_object_or_404(BellSchedule, id=schedule_id, school=request.school)
        schedule = schedules_service.archive_schedule(
            schedule=schedule, actor=request.user, request=request
        )
        return Response(BellScheduleSerializer(schedule).data)


class BellSchedulePeriodsView(SchoolScopedAPIView):
    def put(self, request: Request, schedule_id: int) -> Response:
        schedule = get_object_or_404(BellSchedule, id=schedule_id, school=request.school)
        serializer = PeriodsReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        schedules_service.replace_schedule_periods(
            schedule=schedule,
            actor=request.user,
            periods=serializer.validated_data["periods"],
            request=request,
        )
        schedule.refresh_from_db()
        return Response(BellScheduleSerializer(schedule).data)


class WeekDaysView(SchoolScopedAPIView):
    def get(self, request: Request) -> Response:
        days = week_days_service.get_or_bootstrap_week_days(school=request.school)
        return Response({"days": [serialize_week_day(d) for d in days]})

    def put(self, request: Request) -> Response:
        serializer = WeekDaysReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        days = week_days_service.update_week_days(
            school=request.school,
            actor=request.user,
            items=serializer.validated_data["days"],
            request=request,
        )
        return Response({"days": [serialize_week_day(d) for d in days]})

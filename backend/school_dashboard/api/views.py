"""‏API لوحة إدارة المدرسة — طبقة قراءة فقط فوق أنظمة قائمة (م15).

- المدرسة من `request.school` حصرًا؛ لا `school_id` من العميل.
- المدير والوكيل فقط: المرشد لديه لوحته (م14) والمعلم لا لوحة تنفيذية له.
- كل استجابة تحمل سياقها (العام/الفصل/المنطقة الزمنية/النطاق) حتى لا تُقرأ
  أرقامها خارج سياقها.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from school_dashboard import cache as dashboard_cache
from school_dashboard.ranges import (
    academic_context,
    compare,
    resolve_range,
    resolve_scope,
)
from school_dashboard.selectors import attendance as attendance_selectors
from school_dashboard.selectors import attention as attention_selectors
from school_dashboard.selectors import followup as followup_selectors
from school_dashboard.selectors import reports as report_selectors

#: اللوحة التنفيذية للمدير والوكيل — المرشد والمعلم خارجها (بنود 82-85)
DASHBOARD_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)


class _DashboardView(SchoolScopedAPIView):
    read_roles = DASHBOARD_ROLES
    write_roles = DASHBOARD_ROLES

    def context(self, request):
        """النطاق + الفلاتر + السياق الأكاديمي — يتحقق من كل مدخلات العميل."""
        date_range = resolve_range(school=request.school, params=request.query_params)
        scope = resolve_scope(school=request.school, params=request.query_params)
        return date_range, scope

    def cache_parts(self, request, date_range, scope) -> dict:
        return {
            "range": date_range.as_dict(),
            "scope": scope,
            # الأدوار جزء من المفتاح: لو تغير نطاق الرؤية بالدور لاحقًا لا يتسرب
            "roles": sorted(request.school_roles or []),
        }


class DashboardOverviewView(_DashboardView):
    """الاستجابة الرئيسية للصفحة الأولى — مختصرة وسريعة (بند 66).

    لا تحمل قوائم طلاب ولا نصوصًا حساسة: أرقام فقط + روابط التعمق.
    """

    @extend_schema(responses=None)
    def get(self, request):
        date_range, scope = self.context(request)
        school = request.school
        previous = date_range.previous()

        def build():
            current_kpis = attendance_selectors.attendance_kpis(
                school=school, date_range=date_range, scope=scope
            )
            previous_kpis = attendance_selectors.attendance_kpis(
                school=school, date_range=previous, scope=scope
            )
            return {
                "context": {
                    **academic_context(school),
                    "range": date_range.as_dict(),
                    "previous_range": previous.as_dict(),
                    "scope": scope,
                },
                "today_operations": attendance_selectors.today_operations(school=school),
                "attendance": current_kpis,
                "comparison": _comparison(current_kpis, previous_kpis),
                "warnings": followup_selectors.warning_metrics(
                    school=school, date_range=date_range, scope=scope
                ),
                "actions": followup_selectors.action_metrics(
                    school=school, date_range=date_range, scope=scope
                ),
                "documents": followup_selectors.document_metrics(
                    school=school, date_range=date_range, scope=scope
                ),
                "referrals": followup_selectors.referral_metrics(
                    school=school, date_range=date_range, scope=scope
                ),
                "counseling": followup_selectors.counseling_metrics(
                    school=school, date_range=date_range, scope=scope
                ),
            }

        key = dashboard_cache.build_key(
            school_id=school.id,
            section="overview",
            parts=self.cache_parts(request, date_range, scope),
        )
        # اليوم الجاري يتغير كل لحظة — أجل أقصر من بقية النطاقات
        ttl = (
            dashboard_cache.TTL_TODAY
            if date_range.preset == "TODAY"
            else dashboard_cache.TTL_OVERVIEW
        )
        return Response(dashboard_cache.cached(key=key, ttl=ttl, builder=build))


def _comparison(current: dict, previous: dict) -> dict:
    """مقارنة المؤشرات الأساسية فقط — لا مقارنة لكل رقم بلا معنى."""
    fields = (
        "unexcused_full_absence_days",
        "full_absence_days",
        "partial_absence_days",
        "morning_late_occurrences",
        "absent_periods",
    )
    return {field: compare(current[field], previous[field]) for field in fields}


class DashboardTodayView(_DashboardView):
    """تشغيل الحصة الجارية — أقصر أجل كاش لأنه يتغير كل دقيقة."""

    @extend_schema(responses=None)
    def get(self, request):
        school = request.school
        key = dashboard_cache.build_key(
            school_id=school.id,
            section="today",
            parts={"roles": sorted(request.school_roles or [])},
        )
        return Response(
            dashboard_cache.cached(
                key=key,
                ttl=dashboard_cache.TTL_TODAY,
                builder=lambda: attendance_selectors.today_operations(school=school),
            )
        )


class DashboardTrendView(_DashboardView):
    @extend_schema(responses=None)
    def get(self, request):
        date_range, scope = self.context(request)
        school = request.school
        key = dashboard_cache.build_key(
            school_id=school.id,
            section="trend",
            parts=self.cache_parts(request, date_range, scope),
        )
        return Response(
            dashboard_cache.cached(
                key=key,
                ttl=dashboard_cache.TTL_TREND,
                builder=lambda: {
                    "context": {"range": date_range.as_dict(), "scope": scope},
                    **attendance_selectors.attendance_trend(
                        school=school, date_range=date_range, scope=scope
                    ),
                },
            )
        )


class DashboardSectionsView(_DashboardView):
    @extend_schema(responses=None)
    def get(self, request):
        date_range, scope = self.context(request)
        school = request.school
        key = dashboard_cache.build_key(
            school_id=school.id,
            section="sections",
            parts=self.cache_parts(request, date_range, scope),
        )
        return Response(
            dashboard_cache.cached(
                key=key,
                ttl=dashboard_cache.TTL_OVERVIEW,
                builder=lambda: {
                    "context": {"range": date_range.as_dict(), "scope": scope},
                    **attendance_selectors.section_breakdown(
                        school=school, date_range=date_range, scope=scope
                    ),
                },
            )
        )


class DashboardAttentionView(_DashboardView):
    """طابور «يحتاج متابعة» — بلا كاش: قائمة عمل يجب أن تكون لحظية."""

    @extend_schema(responses=None)
    def get(self, request):
        return Response(attention_selectors.attention_queue(school=request.school))


class AttendanceReportView(_DashboardView):
    @extend_schema(responses=None)
    def get(self, request):
        date_range, scope = self.context(request)
        return Response(
            {
                "context": {"range": date_range.as_dict(), "scope": scope},
                **report_selectors.absence_report(
                    school=request.school,
                    date_range=date_range,
                    scope=scope,
                    params=request.query_params,
                ),
            }
        )


class LatenessReportView(_DashboardView):
    @extend_schema(responses=None)
    def get(self, request):
        date_range, scope = self.context(request)
        return Response(
            {
                "context": {"range": date_range.as_dict(), "scope": scope},
                **report_selectors.lateness_report(
                    school=request.school,
                    date_range=date_range,
                    scope=scope,
                    params=request.query_params,
                ),
            }
        )


class ReferralsReportView(_DashboardView):
    @extend_schema(responses=None)
    def get(self, request):
        date_range, scope = self.context(request)
        return Response(
            {
                "context": {"range": date_range.as_dict(), "scope": scope},
                **report_selectors.referrals_report(
                    school=request.school,
                    membership=request.membership,
                    roles=request.school_roles,
                    date_range=date_range,
                    params=request.query_params,
                ),
            }
        )

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpenCheck,
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  FileText,
  MessageSquareReply,
  Search,
  Sparkles,
  Target,
  UserRound,
  Waypoints,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey } from "@/features/auth/useMe";
import {
  ACTIVITY_TYPES,
  ACTIVITY_TYPE_LABELS,
  type ActivityType,
  CASE_IMPROVEMENT_LABELS,
  CASE_STATUS_LABELS,
  CLOSURE_REASONS,
  GOAL_TYPES,
  GOAL_TYPE_LABELS,
  type GoalType,
  NEXT_STATUSES,
  REQUEST_TYPES,
  REQUEST_TYPE_LABELS,
  type RequestType,
  SESSION_TYPES,
  SESSION_TYPE_LABELS,
  type SessionType,
  addActivity,
  addGoal,
  addSession,
  changeCaseStatus,
  changePlanStatus,
  closeCase,
  completeActivity,
  createPlan,
  getCase,
  getCaseTeacherRequests,
  getCaseTimeline,
  getPlans,
  getSchoolTeachers,
  getSessions,
  reopenCase,
  requestTeacherFollowUp,
  updateGoalStatus,
} from "@/features/counseling/api";
import { useActiveSchoolId, useActiveSchoolType } from "@/features/settings/hooks";
import { localIsoDate } from "@/utils/dates";
import { roleGenitivePluralLabel, roleLabel, studentLabel } from "@/utils/roles";

type Tab = "overview" | "sessions" | "plan" | "requests" | "timeline";

const TABS: [Tab, string][] = [
  ["overview", "نظرة عامة"],
  ["sessions", "الجلسات"],
  ["plan", "خطة المتابعة"],
  ["requests", "طلبات المعلمين"],
  ["timeline", "الخط الزمني"],
];

const METRIC_LABELS: Record<string, string> = {
  unexcused_full_absence_days: "غياب بدون عذر (أيام)",
  full_absence_days: "غياب كامل (أيام)",
  partial_absence_days: "غياب جزئي (أيام)",
  absent_periods: "حصص الغياب",
  morning_late_occurrences: "التأخر الصباحي (مرات)",
  warnings_count: "الإنذارات",
  actions_count: "الإجراءات",
};

function sessionTypeLabel(type: SessionType, schoolType: "BOYS" | "GIRLS"): string {
  if (type === "TEACHER_CONSULTATION") {
    return `تشاور مع ${roleLabel("TEACHER", schoolType)}`;
  }
  return SESSION_TYPE_LABELS[type];
}

function activityTypeLabel(type: ActivityType, schoolType: "BOYS" | "GIRLS"): string {
  if (type === "TEACHER_OBSERVATION") {
    return `طلب ملاحظة ${roleLabel("TEACHER", schoolType)}`;
  }
  return ACTIVITY_TYPE_LABELS[type];
}

function metricValue(source: Record<string, unknown>, key: string): string {
  const value = source[key];
  return value === undefined || value === null ? "—" : String(value);
}

/** صفحة ملف المتابعة بتبويباتها (البنود 62-67). */
export function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const id = Number(caseId);
  const schoolId = useActiveSchoolId();
  const schoolType = useActiveSchoolType();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState<unknown>(null);

  const [sessionType, setSessionType] = useState<SessionType>("STUDENT_MEETING");
  const [sessionSummary, setSessionSummary] = useState("");
  const [sessionObservations, setSessionObservations] = useState("");
  const [sessionOutcome, setSessionOutcome] = useState("");
  const [planTitle, setPlanTitle] = useState("");
  const [goalTitle, setGoalTitle] = useState("");
  const [goalType, setGoalType] = useState<GoalType>("ATTENDANCE");
  const [baseline, setBaseline] = useState("");
  const [target, setTarget] = useState("");
  const [activityTitle, setActivityTitle] = useState("");
  const [activityType, setActivityType] = useState<ActivityType>("STUDENT_CHECK_IN");
  const [activityDueDate, setActivityDueDate] = useState("");
  const [teacherId, setTeacherId] = useState("");
  const [teacherSearch, setTeacherSearch] = useState("");
  const [requestType, setRequestType] = useState<RequestType>("CLASSROOM_BEHAVIOR");
  const [question, setQuestion] = useState("");
  const [requestDueDate, setRequestDueDate] = useState("");
  const [closureReason, setClosureReason] = useState("IMPROVED");
  const [improvement, setImprovement] = useState("IMPROVED");
  const [outcomeSummary, setOutcomeSummary] = useState("");
  const [reopenReason, setReopenReason] = useState("");

  const detail = useQuery({
    queryKey: schoolScopedKey(schoolId, "case", id),
    queryFn: ({ signal }) => getCase(id, signal),
    enabled: schoolId > 0 && Number.isInteger(id),
  });
  const sessions = useQuery({
    queryKey: schoolScopedKey(schoolId, "case-sessions", id),
    queryFn: ({ signal }) => getSessions(id, signal),
    enabled: tab === "sessions" && schoolId > 0,
  });
  const plans = useQuery({
    queryKey: schoolScopedKey(schoolId, "case-plans", id),
    queryFn: ({ signal }) => getPlans(id, signal),
    enabled: tab === "plan" && schoolId > 0,
  });
  const requests = useQuery({
    queryKey: schoolScopedKey(schoolId, "case-requests", id),
    queryFn: ({ signal }) => getCaseTeacherRequests(id, signal),
    enabled: tab === "requests" && schoolId > 0,
  });
  const timeline = useQuery({
    queryKey: schoolScopedKey(schoolId, "case-timeline", id),
    queryFn: ({ signal }) => getCaseTimeline(id, signal),
    enabled: tab === "timeline" && schoolId > 0,
  });
  const teachers = useQuery({
    queryKey: schoolScopedKey(schoolId, "case-teachers"),
    queryFn: ({ signal }) => getSchoolTeachers(signal),
    enabled: tab === "requests" && schoolId > 0,
  });

  const refresh = async (...keys: string[]) => {
    await queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "case", id) });
    for (const key of keys) {
      await queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, key, id) });
    }
  };

  const mutate = <T,>(fn: () => Promise<T>, ...keys: string[]) =>
    fn()
      .then(async () => {
        setError(null);
        await refresh(...keys);
      })
      .catch(setError);

  const statusMutation = useMutation({
    mutationFn: (next: (typeof NEXT_STATUSES)["OPEN"][number]) => changeCaseStatus(id, next),
    onSuccess: () => refresh(),
    onError: setError,
  });

  if (detail.isPending) return <Spinner />;
  if (detail.isError) return <ErrorState error={detail.error} />;
  if (!detail.data) return null;

  const data = detail.data;
  const activePlan = (plans.data ?? []).find((plan) => plan.status === "ACTIVE");
  const canManage = data.can_manage && data.status !== "CLOSED";

  const hasValidGoalNumbers = [baseline, target].every((value) => value === "" || (Number.isFinite(Number(value)) && Number(value) >= 0));
  const teacherOptions = (teachers.data ?? []).filter((teacher) =>
    teacher.name.toLocaleLowerCase("ar").includes(teacherSearch.trim().toLocaleLowerCase("ar")),
  );

  return (
    <div className="ds-page" data-testid="case-detail">
      <PageHeader
        icon={ClipboardList}
        eyebrow="ملف متابعة إرشادي"
        title={data.student_name}
        description={`${data.grade_name ?? "—"} / ${data.section_name ?? "—"} · ${data.referral_category_label} — ${data.referral_reason_label}`}
        tone="counselor"
        badge={<span data-testid="case-status">{data.status_label}</span>}
        meta={<><span>فُتح في {data.opened_at.slice(0, 10)}</span><span className="text-white/30">•</span><span>المرشد: {data.counselor_name ?? "—"}</span></>}
        actions={<><Link to="/counselor" className="inline-flex min-h-11 items-center rounded-xl border border-white/15 bg-white/5 px-4 text-sm font-bold text-white transition hover:bg-white/10">العودة للوحة</Link><Link to={`/students/${data.student_id}/attendance`} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-white px-4 text-sm font-bold text-slate-950 shadow-lg transition hover:bg-slate-50"><BookOpenCheck aria-hidden size={17} /> ملف {studentLabel(schoolType, true)}</Link></>}
      />

      {error != null && <ErrorState error={error} />}

      {canManage && NEXT_STATUSES[data.status].length > 0 && (
        <section className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-teal-100 bg-gradient-to-l from-teal-50 to-white p-4 shadow-sm" data-testid="case-actions">
          <div className="flex items-start gap-3"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-teal-950 text-teal-200"><Sparkles aria-hidden size={18} /></span><div><h2 className="font-black text-slate-900">الخطوة التالية في المتابعة</h2><p className="mt-1 text-xs leading-5 text-slate-600">حدّث مرحلة الملف عندما تنجز الإجراء الفعلي؛ يبقى السجل الزمني محفوظًا لكل انتقال.</p></div></div>
          <div className="flex flex-wrap gap-2">
            {NEXT_STATUSES[data.status].map((next) => (
              <Button key={next} variant="secondary" data-testid={`status-${next}`} disabled={statusMutation.isPending} onClick={() => statusMutation.mutate(next)}>{CASE_STATUS_LABELS[next]}</Button>
            ))}
          </div>
        </section>
      )}

      <div
        className="flex snap-x snap-mandatory gap-1 overflow-x-auto rounded-2xl border border-slate-200 bg-white p-1.5 shadow-sm"
        role="tablist"
        aria-label="أقسام ملف المتابعة"
      >
        {TABS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            id={`case-tab-${value}`}
            aria-selected={tab === value}
            tabIndex={tab === value ? 0 : -1}
            onClick={() => setTab(value)}
            className={`min-h-10 shrink-0 snap-start whitespace-nowrap rounded-xl px-3 py-2.5 text-sm font-bold transition ${
              tab === value
                ? "bg-slate-950 text-white shadow-sm"
                : "text-slate-500 hover:bg-slate-50 hover:text-slate-800"
            }`}
          >
            {value === "requests" ? `طلبات ${roleGenitivePluralLabel("TEACHER", schoolType)}` : label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="space-y-4" data-testid="case-overview">
          <section className="grid gap-3 sm:grid-cols-3">
            <button type="button" onClick={() => setTab("sessions")} className="group flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-start shadow-sm transition hover:-translate-y-0.5 hover:border-teal-200 hover:shadow-md"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-teal-50 text-teal-700"><MessageSquareReply aria-hidden size={18} /></span><span><span className="block text-sm font-black text-slate-900">{canManage ? "وثّق جلسة" : "سجل الجلسات"}</span><span className="mt-1 block text-xs leading-5 text-slate-500">{canManage ? "سجّل ما تم في اللقاء أو الاتصال." : "راجع اللقاءات والاتصالات الموثقة دون تعديل."}</span></span></button>
            <button type="button" onClick={() => setTab("plan")} className="group flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-start shadow-sm transition hover:-translate-y-0.5 hover:border-teal-200 hover:shadow-md"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-violet-50 text-violet-700"><ClipboardList aria-hidden size={18} /></span><span><span className="block text-sm font-black text-slate-900">{canManage ? "خطة وإجراءات" : "خطة المتابعة"}</span><span className="mt-1 block text-xs leading-5 text-slate-500">{canManage ? "حوّل المتابعة إلى أهداف ومواعيد واضحة." : "اطّلع على الأهداف والإجراءات ومواعيدها."}</span></span></button>
            <button type="button" onClick={() => setTab("requests")} className="group flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-start shadow-sm transition hover:-translate-y-0.5 hover:border-teal-200 hover:shadow-md"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-amber-50 text-amber-700"><FileText aria-hidden size={18} /></span><span><span className="block text-sm font-black text-slate-900">{canManage ? "اطلب متابعة" : `طلبات ${roleGenitivePluralLabel("TEACHER", schoolType)}`}</span><span className="mt-1 block text-xs leading-5 text-slate-500">{canManage ? `اطلب ملاحظة مهنية من ${roleLabel("TEACHER", schoolType)}.` : "تابع الطلبات والردود المسجلة في الملف."}</span></span></button>
          </section>

          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <table className="block w-full text-sm md:table">
              <thead className="hidden bg-slate-50 text-slate-600 md:table-header-group">
                <tr>
                  <th className="p-3 text-start">المؤشر</th>
                  <th className="p-3 text-start">عند فتح الملف</th>
                  <th className="p-3 text-start">حاليًا</th>
                </tr>
              </thead>
              <tbody className="grid gap-3 p-3 md:table-row-group md:p-0" data-testid="case-metrics">
                {Object.entries(METRIC_LABELS).map(([key, label]) => (
                  <tr key={key} className="grid grid-cols-2 gap-3 rounded-2xl border border-slate-200 p-4 md:table-row md:border-x-0 md:border-t-0 md:p-0" data-testid={`metric-${key}`}>
                    <td className="col-span-2 p-0 font-black text-slate-900 md:table-cell md:p-3 md:font-normal">{label}</td>
                    <td className="rounded-xl bg-slate-50 p-3 md:table-cell md:rounded-none md:bg-transparent"><span className="mb-1 block text-[11px] font-bold text-slate-500 md:hidden">عند فتح الملف</span>{metricValue(data.snapshot_at_opening, key)}</td>
                    <td className="rounded-xl bg-teal-50 p-3 font-black text-teal-900 md:table-cell md:rounded-none md:bg-transparent md:font-normal md:text-inherit"><span className="mb-1 block text-[11px] font-bold text-teal-700 md:hidden">حاليًا</span>{metricValue(data.current_metrics, key)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
            <p className="font-black text-slate-900">سبب الإحالة</p>
            <p className="mt-2 leading-6 text-slate-700">{data.referral.description}</p>
            <p className="mt-3 border-t border-slate-100 pt-3 text-xs text-slate-600">
              فُتح الملف: {data.opened_at.slice(0, 10)} — بواسطة {data.opened_by_name ?? "—"}
            </p>
            {data.status === "CLOSED" && (
              <p className="mt-2 text-slate-700" data-testid="closure-summary">
                أُغلق: {(data.closed_at ?? "").slice(0, 10)} — السبب:{" "}
                {CLOSURE_REASONS[data.closure_reason] ?? data.closure_reason}
                {data.improvement_status &&
                  ` — النتيجة: ${CASE_IMPROVEMENT_LABELS[data.improvement_status] ?? data.improvement_status}`}
              </p>
            )}
          </div>

          {data.can_manage && data.status !== "CLOSED" && (
            <div className="space-y-3 rounded-2xl border border-amber-200 bg-amber-50/40 p-4 shadow-sm">
              <div className="flex items-start gap-2"><CalendarClock aria-hidden size={18} className="mt-0.5 text-amber-700" /><div><p className="font-black text-slate-900">إغلاق الملف</p><p className="mt-1 text-xs leading-5 text-slate-600">سجّل نتيجة المتابعة قبل الإغلاق حتى تبقى المراجعة الإدارية واضحة.</p></div></div>
              <div className="flex flex-wrap items-end gap-3">
                <label className="flex flex-col gap-1 text-sm">
                  سبب الإغلاق
                  <select
                    data-testid="closure-reason"
                    value={closureReason}
                    onChange={(event) => setClosureReason(event.target.value)}
                    className="rounded-lg border border-slate-300 px-3 py-2"
                  >
                    {Object.entries(CLOSURE_REASONS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  النتيجة
                  <select
                    data-testid="closure-improvement"
                    value={improvement}
                    onChange={(event) => setImprovement(event.target.value)}
                    className="rounded-lg border border-slate-300 px-3 py-2"
                  >
                    {Object.entries(CASE_IMPROVEMENT_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex w-full min-w-0 flex-1 flex-col gap-1 text-sm sm:min-w-56">
                  ملخص النتيجة <span className="text-xs font-normal text-slate-500">اختياري</span>
                  <textarea
                    data-testid="closure-outcome-summary"
                    value={outcomeSummary}
                    onChange={(event) => setOutcomeSummary(event.target.value)}
                    rows={2}
                    placeholder="ما الذي تحقق في المتابعة؟"
                    className="rounded-xl border border-slate-300 px-3 py-2"
                  />
                </label>
                <Button
                  variant="danger"
                  data-testid="close-case"
                  onClick={() =>
                    mutate(() =>
                      closeCase(id, {
                        closure_reason: closureReason,
                        improvement_status: improvement,
                        outcome_summary: outcomeSummary.trim() || undefined,
                      }),
                    )
                  }
                >
                  إغلاق الملف
                </Button>
              </div>
            </div>
          )}

          {data.can_manage && data.status === "CLOSED" && (
            <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <label className="flex flex-col gap-1 text-sm">
                سبب إعادة الفتح
                <input
                  data-testid="reopen-reason"
                  value={reopenReason}
                  onChange={(event) => setReopenReason(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <Button
                data-testid="reopen-case"
                disabled={reopenReason.trim().length === 0}
                onClick={() => mutate(() => reopenCase(id, reopenReason))}
              >
                إعادة فتح الملف
              </Button>
            </div>
          )}
        </div>
      )}

      {tab === "sessions" && (
        <div className="space-y-4" data-testid="case-sessions">
          {canManage && (
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="flex items-start gap-3 border-b border-teal-100 bg-gradient-to-l from-teal-50 to-white p-4 sm:p-5">
                <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-teal-950 text-teal-200">
                  <MessageSquareReply aria-hidden size={18} />
                </span>
                <div>
                  <h2 className="font-black text-slate-900">توثيق جلسة متابعة</h2>
                  <p className="mt-1 text-xs leading-5 text-slate-500">اكتب الوقائع التربوية وما تم الاتفاق عليه؛ تجنّب أي تشخيص طبي أو نفسي.</p>
                </div>
              </div>
              <div className="space-y-4 p-4 sm:p-5">
              <label className="flex max-w-sm flex-col gap-1 text-sm font-bold text-slate-700">
                نوع الجلسة
                <select
                  data-testid="session-type"
                  value={sessionType}
                  onChange={(event) => setSessionType(event.target.value as SessionType)}
                  className="min-h-11 rounded-xl border border-slate-300 bg-white px-3 py-2 outline-none focus:border-teal-500 focus:ring-4 focus:ring-teal-500/10"
                >
                  {SESSION_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {sessionTypeLabel(type, schoolType)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm font-bold text-slate-700">
                ملخص الجلسة
                <textarea
                  data-testid="session-summary"
                  value={sessionSummary}
                  onChange={(event) => setSessionSummary(event.target.value)}
                  rows={3}
                  placeholder="ما الذي تم خلال الجلسة؟"
                  className="rounded-xl border border-slate-300 px-3 py-2.5 outline-none focus:border-teal-500 focus:ring-4 focus:ring-teal-500/10"
                />
              </label>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="flex flex-col gap-1 text-sm font-bold text-slate-700">ملاحظات مهنية <span className="text-xs font-normal text-slate-500">اختياري</span><textarea data-testid="session-observations" value={sessionObservations} onChange={(event) => setSessionObservations(event.target.value)} rows={3} placeholder="سلوك أو مشاركة يمكن ملاحظتها" className="rounded-xl border border-slate-300 px-3 py-2.5 outline-none focus:border-teal-500 focus:ring-4 focus:ring-teal-500/10" /></label>
                <label className="flex flex-col gap-1 text-sm font-bold text-slate-700">نتيجة اللقاء <span className="text-xs font-normal text-slate-500">اختياري</span><textarea data-testid="session-outcome" value={sessionOutcome} onChange={(event) => setSessionOutcome(event.target.value)} rows={3} placeholder="الإجراء أو الاتفاق التالي" className="rounded-xl border border-slate-300 px-3 py-2.5 outline-none focus:border-teal-500 focus:ring-4 focus:ring-teal-500/10" /></label>
              </div>
              <Button
                data-testid="save-session"
                disabled={sessionSummary.trim().length === 0}
                onClick={() =>
                  mutate(async () => {
                    await addSession(id, {
                      session_type: sessionType,
                      summary: sessionSummary,
                      observations: sessionObservations.trim() || undefined,
                      outcome: sessionOutcome.trim() || undefined,
                    });
                    setSessionSummary("");
                    setSessionObservations("");
                    setSessionOutcome("");
                  }, "case-sessions", "case-timeline")
                }
              >
                تسجيل الجلسة
              </Button>
              </div>
            </div>
          )}

          {sessions.isPending ? (
            <Spinner />
          ) : (sessions.data ?? []).length === 0 ? (
            <p className="rounded-xl border border-slate-200 bg-white p-6 text-slate-600 shadow-sm">
              لا توجد جلسات مسجلة.
            </p>
          ) : (
            <ul className="grid gap-3">
              {(sessions.data ?? []).map((session) => (
                <li key={session.id} className={`rounded-2xl border bg-white p-4 shadow-sm ${session.status === "VOIDED" ? "border-red-200 opacity-75" : "border-slate-200"}`} data-testid={`session-${session.id}`}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-teal-50 text-teal-700"><MessageSquareReply aria-hidden size={18} /></span>
                      <div><p className="font-black text-slate-900">{session.session_type_label}</p><p className="mt-0.5 text-xs text-slate-500">بواسطة {session.created_by_name ?? "—"}</p></div>
                    </div>
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-600">{session.occurred_at.slice(0, 10)}</span>
                  </div>
                  <p className="mt-4 rounded-xl bg-slate-50 p-3 text-sm leading-6 text-slate-800">{session.summary}</p>
                  {session.observations && (
                    <div className="mt-3"><p className="text-xs font-bold text-slate-500">ملاحظات مهنية</p><p className="mt-1 text-sm leading-6 text-slate-700">{session.observations}</p></div>
                  )}
                  {session.outcome && (
                    <div className="mt-3 rounded-xl border border-emerald-100 bg-emerald-50/60 p-3"><p className="text-xs font-bold text-emerald-700">نتيجة اللقاء</p><p className="mt-1 text-sm leading-6 text-slate-700">{session.outcome}</p></div>
                  )}
                  {session.status === "VOIDED" && (
                    <p className="mt-3 rounded-lg bg-red-50 p-2 text-sm font-bold text-red-700">ملغاة — {session.void_reason}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tab === "plan" && (
        <div className="space-y-3" data-testid="case-plan">
          {canManage && !activePlan && (
            <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-violet-100 bg-gradient-to-l from-violet-50 to-white p-4 shadow-sm sm:p-5">
              <span className="grid size-10 shrink-0 place-items-center self-start rounded-xl bg-violet-100 text-violet-700"><ClipboardList aria-hidden size={18} /></span>
              <label className="flex w-full min-w-0 flex-1 flex-col gap-1 text-sm font-bold text-slate-700 sm:min-w-60">
                خطة متابعة جديدة
                <input
                  data-testid="plan-title"
                  value={planTitle}
                  onChange={(event) => setPlanTitle(event.target.value)}
                  placeholder="مثال: خطة تحسين المواظبة"
                  className="min-h-11 rounded-xl border border-slate-300 bg-white px-3 py-2 outline-none focus:border-violet-500 focus:ring-4 focus:ring-violet-500/10"
                />
              </label>
              <Button
                data-testid="create-plan"
                disabled={planTitle.trim().length === 0}
                onClick={() =>
                  mutate(async () => {
                    await createPlan(id, {
                      title: planTitle,
                      start_date: localIsoDate(),
                      activate: true,
                    });
                    setPlanTitle("");
                  }, "case-plans", "case-timeline")
                }
              >
                إنشاء الخطة وتفعيلها
              </Button>
            </div>
          )}

          {plans.isPending ? (
            <Spinner />
          ) : (plans.data ?? []).length === 0 ? (
            <p className="rounded-xl border border-slate-200 bg-white p-6 text-slate-600 shadow-sm">
              لا توجد خطة متابعة بعد.
            </p>
          ) : (
            (plans.data ?? []).map((plan) => (
              <div
                key={plan.id}
                className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
                data-testid={`plan-${plan.id}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 bg-slate-50/70 p-4 sm:p-5">
                  <div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-violet-100 text-violet-700"><ClipboardList aria-hidden size={18} /></span><div><p className="font-black text-slate-900">{plan.title}</p><p className="mt-0.5 text-xs text-slate-500">بدأت في {plan.start_date} · بواسطة {plan.created_by_name ?? "—"}</p></div></div>
                  <span className={`rounded-full px-3 py-1 text-xs font-bold ${plan.status === "ACTIVE" ? "bg-teal-100 text-teal-800" : plan.status === "COMPLETED" ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-700"}`} data-testid={`plan-status-${plan.id}`}>
                    {plan.status_label}
                  </span>
                </div>

                <div className="grid gap-4 p-4 sm:p-5 lg:grid-cols-2">
                <div>
                  <p className="mb-2 flex items-center gap-2 text-sm font-black text-slate-900"><Target aria-hidden size={17} className="text-violet-600" />الأهداف</p>
                  <ul className="space-y-2 text-sm">
                    {plan.goals.map((goal) => (
                      <li key={goal.id} className="rounded-xl border border-slate-100 bg-slate-50/70 p-3" data-testid={`goal-${goal.id}`}>
                        <div className="flex flex-wrap items-start justify-between gap-2"><span className="font-bold text-slate-800">
                          {goal.title} ({goal.goal_type_label})
                          {goal.baseline_value !== null && goal.target_value !== null
                            ? ` — من ${goal.baseline_value} إلى ${goal.target_value} ${goal.unit}`
                            : ""}
                        </span><span className="rounded-full bg-white px-2 py-0.5 text-xs font-bold text-slate-600 ring-1 ring-slate-200">{goal.status_label}</span></div>
                        {canManage && plan.status === "ACTIVE" && goal.status === "OPEN" && (
                          <button
                            type="button"
                            data-testid={`complete-goal-${goal.id}`}
                            className="mt-2 inline-flex min-h-8 items-center gap-1.5 rounded-lg bg-emerald-50 px-2.5 text-xs font-bold text-emerald-700 hover:bg-emerald-100"
                            onClick={() =>
                              mutate(
                                () => updateGoalStatus(goal.id, "COMPLETED"),
                                "case-plans",
                                "case-timeline",
                              )
                            }
                          >
                            <CheckCircle2 aria-hidden size={14} /> تحقق الهدف
                          </button>
                        )}
                      </li>
                    ))}
                    {plan.goals.length === 0 && <li className="text-slate-600">لا أهداف بعد.</li>}
                  </ul>
                </div>

                <div>
                  <p className="mb-2 flex items-center gap-2 text-sm font-black text-slate-900"><CalendarClock aria-hidden size={17} className="text-teal-600" />الإجراءات</p>
                  <ul className="space-y-2 text-sm">
                    {plan.activities.map((activity) => (
                      <li
                        key={activity.id}
                        className="rounded-xl border border-slate-100 bg-slate-50/70 p-3"
                        data-testid={`activity-${activity.id}`}
                      >
                        <div className="flex flex-wrap items-start justify-between gap-2"><span className="font-bold text-slate-800">
                          {activity.title} ({activity.activity_type_label})
                          {activity.due_date ? ` — ${activity.due_date}` : ""}
                        </span><span className="rounded-full bg-white px-2 py-0.5 text-xs font-bold text-slate-600 ring-1 ring-slate-200">{activity.status_label}</span></div>
                        {canManage && plan.status === "ACTIVE" && activity.status === "PENDING" && (
                          <button
                            type="button"
                            data-testid={`complete-activity-${activity.id}`}
                            className="mt-2 inline-flex min-h-8 items-center gap-1.5 rounded-lg bg-emerald-50 px-2.5 text-xs font-bold text-emerald-700 hover:bg-emerald-100"
                            onClick={() =>
                              mutate(
                                () => completeActivity(activity.id),
                                "case-plans",
                                "case-timeline",
                              )
                            }
                          >
                            <CheckCircle2 aria-hidden size={14} /> تم التنفيذ
                          </button>
                        )}
                      </li>
                    ))}
                    {plan.activities.length === 0 && (
                      <li className="text-slate-600">لا إجراءات بعد.</li>
                    )}
                  </ul>
                </div>
                </div>

                {canManage && plan.status === "ACTIVE" && (
                  <div className="space-y-4 border-t border-slate-100 bg-slate-50/40 p-4 sm:p-5">
                    <div className="flex flex-wrap items-end gap-3">
                      <label className="flex flex-col gap-1 text-sm">
                        هدف جديد
                        <input
                          data-testid="goal-title"
                          value={goalTitle}
                          onChange={(event) => setGoalTitle(event.target.value)}
                          className="rounded-lg border border-slate-300 px-3 py-2"
                        />
                      </label>
                      <label className="flex flex-col gap-1 text-sm">
                        النوع
                        <select
                          data-testid="goal-type"
                          value={goalType}
                          onChange={(event) => setGoalType(event.target.value as GoalType)}
                          className="rounded-lg border border-slate-300 px-3 py-2"
                        >
                          {GOAL_TYPES.map((type) => (
                            <option key={type} value={type}>
                              {GOAL_TYPE_LABELS[type]}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="flex flex-col gap-1 text-sm">
                        من
                        <input
                          data-testid="goal-baseline"
                          value={baseline}
                          onChange={(event) => setBaseline(event.target.value)}
                          className="w-20 rounded-lg border border-slate-300 px-3 py-2"
                        />
                      </label>
                      <label className="flex flex-col gap-1 text-sm">
                        إلى
                        <input
                          data-testid="goal-target"
                          value={target}
                          onChange={(event) => setTarget(event.target.value)}
                          className="w-20 rounded-lg border border-slate-300 px-3 py-2"
                        />
                      </label>
                      <Button
                        data-testid="add-goal"
                        disabled={goalTitle.trim().length === 0 || !hasValidGoalNumbers}
                        onClick={() =>
                          mutate(async () => {
                            await addGoal(plan.id, {
                              goal_type: goalType,
                              title: goalTitle,
                              baseline_value: baseline === "" ? null : Number(baseline),
                              target_value: target === "" ? null : Number(target),
                            });
                            setGoalTitle("");
                            setBaseline("");
                            setTarget("");
                          }, "case-plans", "case-timeline")
                        }
                      >
                        إضافة هدف
                      </Button>
                    </div>

                    <div className="flex flex-wrap items-end gap-2 rounded-xl bg-slate-50 p-3">
                      <label className="flex w-full min-w-0 flex-1 flex-col gap-1 text-sm sm:min-w-48">
                        إجراء جديد
                        <input
                          data-testid="activity-title"
                          value={activityTitle}
                          onChange={(event) => setActivityTitle(event.target.value)}
                          className="rounded-lg border border-slate-300 px-3 py-2"
                        />
                      </label>
                      <label className="flex flex-col gap-1 text-sm">
                        النوع
                        <select
                          data-testid="activity-type"
                          value={activityType}
                          onChange={(event) => setActivityType(event.target.value as ActivityType)}
                          className="rounded-lg border border-slate-300 px-3 py-2"
                        >
                          {ACTIVITY_TYPES.map((type) => (
                            <option key={type} value={type}>
                              {activityTypeLabel(type, schoolType)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="flex flex-col gap-1 text-sm">
                        تاريخ الاستحقاق <span className="text-xs text-slate-500">اختياري</span>
                        <input
                          type="date"
                          data-testid="activity-due-date"
                          value={activityDueDate}
                          onChange={(event) => setActivityDueDate(event.target.value)}
                          className="rounded-xl border border-slate-300 px-3 py-2"
                        />
                      </label>
                      <Button
                        data-testid="add-activity"
                        disabled={activityTitle.trim().length === 0}
                        onClick={() =>
                          mutate(async () => {
                            await addActivity(plan.id, {
                              activity_type: activityType,
                              title: activityTitle,
                              due_date: activityDueDate || undefined,
                            });
                            setActivityTitle("");
                            setActivityDueDate("");
                          }, "case-plans", "case-timeline")
                        }
                      >
                        إضافة إجراء
                      </Button>
                      <Button
                        data-testid={`complete-plan-${plan.id}`}
                        onClick={() =>
                          mutate(
                            () => changePlanStatus(plan.id, "COMPLETED"),
                            "case-plans",
                            "case-timeline",
                          )
                        }
                      >
                        إنهاء الخطة
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {tab === "requests" && (
        <div className="space-y-4" data-testid="case-requests">
          {canManage && (
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="flex items-start gap-3 border-b border-amber-100 bg-gradient-to-l from-amber-50 to-white p-4 sm:p-5"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-amber-100 text-amber-700"><UserRound aria-hidden size={18} /></span><div><h2 className="font-black text-slate-900">طلب متابعة من {roleLabel("TEACHER", schoolType)}</h2><p className="mt-1 text-xs leading-5 text-slate-500">أرسل سؤالًا محددًا مع موعد رد واضح؛ لا تظهر تفاصيل ملف الحالة لصاحب الطلب.</p></div></div>
              <div className="grid gap-3 p-4 sm:p-5 lg:grid-cols-2">
              {(teachers.data ?? []).length > 8 && (
                <label className="relative flex flex-col gap-1 text-sm font-bold text-slate-700 lg:col-span-2">
                  البحث عن {roleLabel("TEACHER", schoolType)}
                  <span className="relative"><Search aria-hidden size={17} className="pointer-events-none absolute end-3 top-1/2 -translate-y-1/2 text-slate-400" /><input type="search" data-testid="teacher-search" value={teacherSearch} onChange={(event) => setTeacherSearch(event.target.value)} placeholder={`اكتب اسم ${roleLabel("TEACHER", schoolType)} لتقليص القائمة`} className="min-h-11 w-full rounded-xl border border-slate-300 px-3 pe-10 font-normal outline-none focus:border-amber-500 focus:ring-4 focus:ring-amber-500/10" /></span>
                </label>
              )}
              <label className="flex flex-col gap-1 text-sm font-bold text-slate-700">
                {roleLabel("TEACHER", schoolType)}
                <select
                  data-testid="request-teacher"
                  value={teacherId}
                  onChange={(event) => setTeacherId(event.target.value)}
                  className="min-h-11 rounded-xl border border-slate-300 bg-white px-3 py-2 font-normal outline-none focus:border-amber-500 focus:ring-4 focus:ring-amber-500/10"
                >
                  <option value="">اختر {roleLabel("TEACHER", schoolType)}</option>
                  {teacherOptions.map((teacher) => (
                    <option key={teacher.membership_id} value={teacher.membership_id}>
                      {teacher.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm font-bold text-slate-700">
                نوع الملاحظة
                <select
                  data-testid="request-type"
                  value={requestType}
                  onChange={(event) => setRequestType(event.target.value as RequestType)}
                  className="min-h-11 rounded-xl border border-slate-300 bg-white px-3 py-2 font-normal outline-none focus:border-amber-500 focus:ring-4 focus:ring-amber-500/10"
                >
                  {REQUEST_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {REQUEST_TYPE_LABELS[type]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm font-bold text-slate-700 lg:col-span-2">
                السؤال
                <input
                  data-testid="request-question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder={`اكتب سؤالًا محددًا يمكن ${schoolType === "GIRLS" ? "للمعلمة" : "للمعلم"} الإجابة عنه`}
                  className="min-h-11 rounded-xl border border-slate-300 px-3 py-2 font-normal outline-none focus:border-amber-500 focus:ring-4 focus:ring-amber-500/10"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm font-bold text-slate-700">
                موعد الرد <span className="text-xs text-slate-500">اختياري</span>
                <input
                  type="date"
                  data-testid="request-due-date"
                  value={requestDueDate}
                  onChange={(event) => setRequestDueDate(event.target.value)}
                  className="min-h-11 rounded-xl border border-slate-300 px-3 py-2 font-normal outline-none focus:border-amber-500 focus:ring-4 focus:ring-amber-500/10"
                />
              </label>
              <Button
                className="self-end"
                data-testid="send-request"
                disabled={teacherId === "" || question.trim().length === 0}
                onClick={() =>
                  mutate(async () => {
                    await requestTeacherFollowUp(id, {
                      teacher_membership_id: Number(teacherId),
                      request_type: requestType,
                      question,
                      due_date: requestDueDate || undefined,
                    });
                    setQuestion("");
                    setRequestDueDate("");
                  }, "case-requests", "case-timeline")
                }
              >
                إرسال الطلب
              </Button>
              </div>
            </div>
          )}

          {requests.isPending ? (
            <Spinner />
          ) : (requests.data ?? []).length === 0 ? (
            <p className="rounded-xl border border-slate-200 bg-white p-6 text-slate-600 shadow-sm">
              لا توجد طلبات متابعة.
            </p>
          ) : (
            <ul className="grid gap-3">
              {(requests.data ?? []).map((row) => (
                <li key={row.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" data-testid={`req-row-${row.id}`}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-amber-50 text-amber-700"><UserRound aria-hidden size={18} /></span><div><p className="font-black text-slate-900">{row.teacher_name ?? "—"}</p><p className="mt-0.5 text-xs text-slate-500">{row.request_type_label}{row.due_date ? ` · الرد قبل ${row.due_date}` : ""}</p></div></div>
                    <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${row.response ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-900"}`}>{row.status_label}</span>
                  </div>
                  <p className="mt-4 rounded-xl bg-slate-50 p-3 text-sm leading-6 text-slate-800">{row.question}</p>
                  {row.response && (
                    <div className="mt-3 rounded-xl border border-emerald-100 bg-emerald-50/60 p-3 text-sm" data-testid={`req-response-${row.id}`}>
                      <p className="text-xs font-bold text-emerald-700">رد {roleLabel("TEACHER", schoolType)}</p>
                      <p className="mt-1 leading-6 text-slate-800">{row.response.observation}</p>
                      <p className="mt-2 text-xs font-bold text-slate-600">
                        التقييم: {row.response.improvement_status_label}
                      </p>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tab === "timeline" && (
        <div data-testid="case-timeline">
          {timeline.isPending ? (
            <Spinner />
          ) : (
            <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="flex items-center justify-between gap-3 border-b border-slate-100 bg-slate-50/70 p-4"><div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-slate-900 text-teal-200"><Waypoints aria-hidden size={18} /></span><div><h2 className="font-black text-slate-900">السجل الزمني للحالة</h2><p className="mt-0.5 text-xs text-slate-500">ترتيب موثّق لأحدث الإجراءات والقرارات.</p></div></div><span className="rounded-full bg-white px-3 py-1 text-xs font-bold text-slate-600 ring-1 ring-slate-200">{(timeline.data ?? []).length} حدثًا</span></div>
            <ul className="p-4 sm:p-5">
              {(timeline.data ?? []).map((event) => (
                <li key={event.id} className="relative flex gap-3 pb-5 last:pb-0 text-sm before:absolute before:bottom-0 before:start-[0.69rem] before:top-6 before:w-px before:bg-slate-200 last:before:hidden">
                  <span className="relative z-10 mt-1 size-6 shrink-0 rounded-full border-4 border-white bg-teal-600 shadow-sm" aria-hidden />
                  <div className="min-w-0 flex-1 rounded-xl bg-slate-50 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-black text-slate-800">{event.event_type_label}</span><span className="text-xs text-slate-500">
                    {event.created_at.slice(0, 10)} · {event.actor_name ?? "—"}
                  </span></div></div>
                </li>
              ))}
            </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

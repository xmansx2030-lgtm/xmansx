import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
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
import { useActiveSchoolId } from "@/features/settings/hooks";
import { localIsoDate } from "@/utils/dates";

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
  period_late_occurrences: "التأخر عن الحصص (مرات)",
  warnings_count: "الإنذارات",
  actions_count: "الإجراءات",
};

function metricValue(source: Record<string, unknown>, key: string): string {
  const value = source[key];
  return value === undefined || value === null ? "—" : String(value);
}

/** صفحة ملف المتابعة بتبويباتها (البنود 62-67). */
export function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const id = Number(caseId);
  const schoolId = useActiveSchoolId();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState<unknown>(null);

  const [sessionType, setSessionType] = useState<SessionType>("STUDENT_MEETING");
  const [sessionSummary, setSessionSummary] = useState("");
  const [planTitle, setPlanTitle] = useState("");
  const [goalTitle, setGoalTitle] = useState("");
  const [goalType, setGoalType] = useState<GoalType>("ATTENDANCE");
  const [baseline, setBaseline] = useState("");
  const [target, setTarget] = useState("");
  const [activityTitle, setActivityTitle] = useState("");
  const [activityType, setActivityType] = useState<ActivityType>("STUDENT_CHECK_IN");
  const [teacherId, setTeacherId] = useState("");
  const [requestType, setRequestType] = useState<RequestType>("CLASSROOM_BEHAVIOR");
  const [question, setQuestion] = useState("");
  const [closureReason, setClosureReason] = useState("IMPROVED");
  const [improvement, setImprovement] = useState("IMPROVED");
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

  return (
    <div className="space-y-5" data-testid="case-detail">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to="/counselor" className="text-sm text-blue-700 underline">
            العودة إلى لوحة الإرشاد
          </Link>
          <h1 className="mt-2 text-2xl font-bold">{data.student_name}</h1>
          <p className="text-sm text-slate-600">
            {data.grade_name ?? "—"} / {data.section_name ?? "—"}
            <span className="mx-2">•</span>
            <span data-testid="case-status">{data.status_label}</span>
            <span className="mx-2">•</span>
            {data.referral_category_label} — {data.referral_reason_label}
          </p>
        </div>
        <Link
          to={`/students/${data.student_id}/attendance`}
          className="text-sm text-blue-700 underline"
        >
          ملف الطالب
        </Link>
      </div>

      {error != null && <ErrorState error={error} />}

      {canManage && (
        <div className="flex flex-wrap items-center gap-2" data-testid="case-actions">
          {NEXT_STATUSES[data.status].map((next) => (
            <Button
              key={next}
              data-testid={`status-${next}`}
              onClick={() => statusMutation.mutate(next)}
            >
              {CASE_STATUS_LABELS[next]}
            </Button>
          ))}
        </div>
      )}

      <div
        className="flex gap-1 overflow-x-auto border-b border-slate-200"
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
            className={`shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-sm ${
              tab === value ? "border-blue-700 text-blue-700" : "border-transparent text-slate-600"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="space-y-4" data-testid="case-overview">
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="p-3 text-start">المؤشر</th>
                  <th className="p-3 text-start">عند فتح الملف</th>
                  <th className="p-3 text-start">حاليًا</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(METRIC_LABELS).map(([key, label]) => (
                  <tr key={key} className="border-b" data-testid={`metric-${key}`}>
                    <td className="p-3">{label}</td>
                    <td className="p-3">{metricValue(data.snapshot_at_opening, key)}</td>
                    <td className="p-3">{metricValue(data.current_metrics, key)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
            <p className="font-semibold">سبب الإحالة</p>
            <p className="text-slate-700">{data.referral.description}</p>
            <p className="mt-2 text-slate-600">
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
            <div className="space-y-2 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="font-semibold">إغلاق الملف</p>
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
                <Button
                  data-testid="close-case"
                  onClick={() =>
                    mutate(() =>
                      closeCase(id, {
                        closure_reason: closureReason,
                        improvement_status: improvement,
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
        <div className="space-y-3" data-testid="case-sessions">
          {canManage && (
            <div className="space-y-2 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <label className="flex flex-col gap-1 text-sm">
                نوع الجلسة
                <select
                  data-testid="session-type"
                  value={sessionType}
                  onChange={(event) => setSessionType(event.target.value as SessionType)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                >
                  {SESSION_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {SESSION_TYPE_LABELS[type]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                ملخص الجلسة
                <textarea
                  data-testid="session-summary"
                  value={sessionSummary}
                  onChange={(event) => setSessionSummary(event.target.value)}
                  rows={2}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <Button
                data-testid="save-session"
                disabled={sessionSummary.trim().length === 0}
                onClick={() =>
                  mutate(async () => {
                    await addSession(id, {
                      session_type: sessionType,
                      summary: sessionSummary,
                    });
                    setSessionSummary("");
                  }, "case-sessions", "case-timeline")
                }
              >
                تسجيل الجلسة
              </Button>
            </div>
          )}

          {sessions.isPending ? (
            <Spinner />
          ) : (sessions.data ?? []).length === 0 ? (
            <p className="rounded-xl border border-slate-200 bg-white p-6 text-slate-600 shadow-sm">
              لا توجد جلسات مسجلة.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white shadow-sm">
              {(sessions.data ?? []).map((session) => (
                <li key={session.id} className="space-y-1 p-4" data-testid={`session-${session.id}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold">{session.session_type_label}</span>
                    <span className="text-sm text-slate-600">
                      {session.occurred_at.slice(0, 10)} · {session.created_by_name ?? "—"}
                    </span>
                  </div>
                  <p className="text-sm text-slate-700">{session.summary}</p>
                  {session.outcome && (
                    <p className="text-sm text-slate-600">النتيجة: {session.outcome}</p>
                  )}
                  {session.status === "VOIDED" && (
                    <p className="text-sm text-red-700">ملغاة — {session.void_reason}</p>
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
            <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <label className="flex flex-col gap-1 text-sm">
                عنوان الخطة
                <input
                  data-testid="plan-title"
                  value={planTitle}
                  onChange={(event) => setPlanTitle(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
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
                className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
                data-testid={`plan-${plan.id}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold">{plan.title}</span>
                  <span className="text-sm text-slate-600" data-testid={`plan-status-${plan.id}`}>
                    {plan.status_label}
                  </span>
                </div>

                <div>
                  <p className="text-sm font-semibold">الأهداف</p>
                  <ul className="space-y-1 text-sm">
                    {plan.goals.map((goal) => (
                      <li key={goal.id} className="flex flex-wrap items-center gap-2" data-testid={`goal-${goal.id}`}>
                        <span>
                          {goal.title} ({goal.goal_type_label})
                          {goal.baseline_value !== null && goal.target_value !== null
                            ? ` — من ${goal.baseline_value} إلى ${goal.target_value} ${goal.unit}`
                            : ""}
                        </span>
                        <span className="text-slate-600">{goal.status_label}</span>
                        {canManage && goal.status === "OPEN" && (
                          <button
                            type="button"
                            data-testid={`complete-goal-${goal.id}`}
                            className="text-blue-700 underline"
                            onClick={() =>
                              mutate(
                                () => updateGoalStatus(goal.id, "COMPLETED"),
                                "case-plans",
                                "case-timeline",
                              )
                            }
                          >
                            تحقق
                          </button>
                        )}
                      </li>
                    ))}
                    {plan.goals.length === 0 && <li className="text-slate-600">لا أهداف بعد.</li>}
                  </ul>
                </div>

                <div>
                  <p className="text-sm font-semibold">الإجراءات</p>
                  <ul className="space-y-1 text-sm">
                    {plan.activities.map((activity) => (
                      <li
                        key={activity.id}
                        className="flex flex-wrap items-center gap-2"
                        data-testid={`activity-${activity.id}`}
                      >
                        <span>
                          {activity.title} ({activity.activity_type_label})
                          {activity.due_date ? ` — ${activity.due_date}` : ""}
                        </span>
                        <span className="text-slate-600">{activity.status_label}</span>
                        {canManage && activity.status === "PENDING" && (
                          <button
                            type="button"
                            data-testid={`complete-activity-${activity.id}`}
                            className="text-blue-700 underline"
                            onClick={() =>
                              mutate(
                                () => completeActivity(activity.id),
                                "case-plans",
                                "case-timeline",
                              )
                            }
                          >
                            تم التنفيذ
                          </button>
                        )}
                      </li>
                    ))}
                    {plan.activities.length === 0 && (
                      <li className="text-slate-600">لا إجراءات بعد.</li>
                    )}
                  </ul>
                </div>

                {canManage && plan.status === "ACTIVE" && (
                  <div className="space-y-3 border-t border-slate-100 pt-3">
                    <div className="flex flex-wrap items-end gap-2">
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
                        disabled={goalTitle.trim().length === 0}
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

                    <div className="flex flex-wrap items-end gap-2">
                      <label className="flex flex-col gap-1 text-sm">
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
                              {ACTIVITY_TYPE_LABELS[type]}
                            </option>
                          ))}
                        </select>
                      </label>
                      <Button
                        data-testid="add-activity"
                        disabled={activityTitle.trim().length === 0}
                        onClick={() =>
                          mutate(async () => {
                            await addActivity(plan.id, {
                              activity_type: activityType,
                              title: activityTitle,
                            });
                            setActivityTitle("");
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
        <div className="space-y-3" data-testid="case-requests">
          {canManage && (
            <div className="flex flex-wrap items-end gap-2 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <label className="flex flex-col gap-1 text-sm">
                المعلم
                <select
                  data-testid="request-teacher"
                  value={teacherId}
                  onChange={(event) => setTeacherId(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                >
                  <option value="">اختر المعلم</option>
                  {(teachers.data ?? []).map((teacher) => (
                    <option key={teacher.membership_id} value={teacher.membership_id}>
                      {teacher.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                نوع الملاحظة
                <select
                  data-testid="request-type"
                  value={requestType}
                  onChange={(event) => setRequestType(event.target.value as RequestType)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                >
                  {REQUEST_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {REQUEST_TYPE_LABELS[type]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                السؤال
                <input
                  data-testid="request-question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <Button
                data-testid="send-request"
                disabled={teacherId === "" || question.trim().length === 0}
                onClick={() =>
                  mutate(async () => {
                    await requestTeacherFollowUp(id, {
                      teacher_membership_id: Number(teacherId),
                      request_type: requestType,
                      question,
                    });
                    setQuestion("");
                  }, "case-requests", "case-timeline")
                }
              >
                إرسال الطلب
              </Button>
            </div>
          )}

          {requests.isPending ? (
            <Spinner />
          ) : (requests.data ?? []).length === 0 ? (
            <p className="rounded-xl border border-slate-200 bg-white p-6 text-slate-600 shadow-sm">
              لا توجد طلبات متابعة.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white shadow-sm">
              {(requests.data ?? []).map((row) => (
                <li key={row.id} className="space-y-1 p-4" data-testid={`req-row-${row.id}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold">
                      {row.request_type_label} — {row.teacher_name ?? "—"}
                    </span>
                    <span className="text-sm text-slate-600">{row.status_label}</span>
                  </div>
                  <p className="text-sm text-slate-700">{row.question}</p>
                  {row.response && (
                    <div className="rounded-lg bg-slate-50 p-2 text-sm" data-testid={`req-response-${row.id}`}>
                      <p>{row.response.observation}</p>
                      <p className="text-slate-600">
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
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white shadow-sm">
              {(timeline.data ?? []).map((event) => (
                <li key={event.id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
                  <span>{event.event_type_label}</span>
                  <span className="text-slate-600">
                    {event.created_at.slice(0, 10)} · {event.actor_name ?? "—"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

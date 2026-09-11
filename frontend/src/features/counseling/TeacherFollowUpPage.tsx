import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  MessageSquareReply,
  Send,
  UserRound,
} from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import {
  IMPROVEMENT_LABELS,
  type TeacherImprovement,
  getMyFollowUpRequests,
  respondToFollowUp,
} from "@/features/counseling/api";
import { useActiveSchoolId } from "@/features/settings/hooks";
import { roleLabel } from "@/utils/roles";

const IMPROVEMENTS = Object.keys(IMPROVEMENT_LABELS) as TeacherImprovement[];

/** صندوق المعلم — طلباته هو فقط: الطالب والسؤال وردّه.
 *  لا يعرض الحالة ولا جلساتها ولا ردود الزملاء (البنود 68-71). */
export function TeacherFollowUpPage() {
  const schoolId = useActiveSchoolId();
  const me = useMe();
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const queryClient = useQueryClient();
  const [openId, setOpenId] = useState<number | null>(null);
  const [observation, setObservation] = useState("");
  const [improvement, setImprovement] = useState<TeacherImprovement>("IMPROVED");
  const [error, setError] = useState<unknown>(null);

  const requests = useQuery({
    queryKey: schoolScopedKey(schoolId, "my-follow-up-requests"),
    queryFn: ({ signal }) => getMyFollowUpRequests(signal),
    enabled: schoolId > 0,
  });

  const submit = async (requestId: number) => {
    try {
      await respondToFollowUp(requestId, {
        observation,
        improvement_status: improvement,
      });
      setOpenId(null);
      setObservation("");
      setError(null);
      await queryClient.invalidateQueries({
        queryKey: schoolScopedKey(schoolId, "my-follow-up-requests"),
      });
    } catch (err) {
      setError(err);
    }
  };

  const closeComposer = () => {
    setOpenId(null);
    setObservation("");
    setImprovement("IMPROVED");
    setError(null);
  };

  const openComposer = (requestId: number) => {
    setOpenId(requestId);
    setObservation("");
    setImprovement("IMPROVED");
    setError(null);
  };

  if (requests.isPending) return <Spinner />;
  if (requests.isError) return <ErrorState error={requests.error} />;

  const rows = requests.data ?? [];
  const pendingCount = rows.filter((row) => !row.response && row.status !== "CANCELLED").length;
  const answeredCount = rows.filter((row) => row.response).length;

  return (
    <div className="ds-page" data-testid="teacher-follow-ups">
      <PageHeader icon={MessageSquareReply} eyebrow={`مساحة ${roleLabel("TEACHER", schoolType)}`} title="طلبات المتابعة" description={`طلبات ملاحظة عن ${schoolType === "GIRLS" ? "طالباتك" : "طلابك"} من ${roleLabel("COUNSELOR", schoolType)}؛ ملاحظتك المهنية تصل إلى ملف المتابعة مباشرة.`} tone="teacher" badge={`${pendingCount} بانتظار ردك`} />

      {error != null && <ErrorState error={error} />}

      {rows.length === 0 ? (
        <EmptyState title="لا توجد طلبات متابعة حاليًا" description="ستظهر هنا الطلبات المرسلة لك من المرشد، مع السؤال والموعد المحدد للرد." icon={ClipboardCheck} testId="no-requests" />
      ) : (
        <>
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-3" aria-label="ملخص طلبات المتابعة">
            <div className="rounded-2xl border border-amber-100 bg-amber-50/70 p-4">
              <Clock3 aria-hidden size={20} className="mb-3 text-amber-600" />
              <p className="text-2xl font-black text-slate-900">{pendingCount}</p>
              <p className="text-sm font-medium text-slate-600">بانتظار ملاحظتك</p>
            </div>
            <div className="rounded-2xl border border-emerald-100 bg-emerald-50/70 p-4">
              <CheckCircle2 aria-hidden size={20} className="mb-3 text-emerald-600" />
              <p className="text-2xl font-black text-slate-900">{answeredCount}</p>
              <p className="text-sm font-medium text-slate-600">تم الرد عليها</p>
            </div>
            <div className="col-span-2 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:col-span-1">
              <ClipboardCheck aria-hidden size={20} className="mb-3 text-slate-500" />
              <p className="text-2xl font-black text-slate-900">{rows.length}</p>
              <p className="text-sm font-medium text-slate-600">إجمالي الطلبات</p>
            </div>
          </section>

          <ul className="grid gap-4">
            {rows.map((row) => (
              <li key={row.id} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:border-slate-300 hover:shadow-md" data-testid={`follow-up-${row.id}`}>
                <div className="space-y-4 p-4 sm:p-5">
                  <div className="flex flex-col items-stretch justify-between gap-3 sm:flex-row sm:items-start">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-teal-50 text-teal-700">
                        <UserRound aria-hidden size={21} />
                      </span>
                      <div className="min-w-0">
                        <p className="break-words font-bold text-slate-900">{row.student_name}</p>
                        <p className="mt-0.5 text-xs text-slate-500">طلب من {row.requested_by_name ?? roleLabel("COUNSELOR", schoolType)}</p>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="rounded-full bg-slate-100 px-2.5 py-1 font-bold text-slate-600">{row.request_type_label}</span>
                      <span className={`rounded-full px-2.5 py-1 font-bold ${row.response ? "bg-emerald-100 text-emerald-800" : row.status === "CANCELLED" ? "bg-slate-100 text-slate-600" : "bg-amber-100 text-amber-900"}`}>{row.status_label}</span>
                    </div>
                  </div>
                  <div className="rounded-xl bg-slate-50 p-4">
                    <p className="text-xs font-bold text-slate-500">المطلوب ملاحظته</p>
                    <p className="mt-1.5 text-sm font-medium leading-6 text-slate-800">{row.question}</p>
                    {row.due_date && <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-slate-500"><CalendarDays aria-hidden size={14} />موعد الرد: {row.due_date}</p>}
                  </div>

              {row.response ? (
                <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-4 text-sm" data-testid={`my-response-${row.id}`}>
                  <p className="mb-1 text-xs font-bold text-emerald-700">ملاحظتك المرسلة</p>
                  <p className="leading-6 text-slate-800">{row.response.observation}</p>
                  <p className="mt-2 text-xs font-bold text-slate-600">التقييم: {row.response.improvement_status_label}</p>
                </div>
              ) : openId === row.id ? (
                <div className="space-y-3 rounded-xl border border-teal-100 bg-teal-50/40 p-4">
                  <label className="block text-sm font-bold text-slate-700" htmlFor={`observation-${row.id}`}>
                    ملاحظتك المهنية
                  </label>
                  <textarea
                    id={`observation-${row.id}`}
                    data-testid="response-observation"
                    value={observation}
                    onChange={(event) => setObservation(event.target.value)}
                    rows={4}
                    placeholder="اكتب ما لاحظته داخل الفصل بوضوح واختصار..."
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none transition focus:border-teal-500 focus:ring-4 focus:ring-teal-500/10"
                  />
                  <div className="flex flex-col items-stretch justify-between gap-3 sm:flex-row sm:items-end">
                    <label className="flex w-full min-w-0 flex-col gap-1 text-sm font-bold text-slate-700 sm:w-auto sm:min-w-48">
                      التقييم
                      <select
                        data-testid="response-improvement"
                        value={improvement}
                        onChange={(event) =>
                          setImprovement(event.target.value as TeacherImprovement)
                        }
                        className="min-h-11 rounded-xl border border-slate-300 bg-white px-3 py-2 font-normal outline-none focus:border-teal-500 focus:ring-4 focus:ring-teal-500/10"
                      >
                        {IMPROVEMENTS.map((value) => (
                          <option key={value} value={value}>
                            {IMPROVEMENT_LABELS[value]}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="grid gap-2 sm:flex">
                      <Button variant="secondary" className="w-full justify-center sm:w-auto" onClick={closeComposer} data-testid="cancel-response">إلغاء</Button>
                      <Button
                        className="w-full justify-center sm:w-auto"
                        data-testid="submit-response"
                        disabled={observation.trim().length === 0}
                        onClick={() => submit(row.id)}
                      >
                        <Send aria-hidden size={16} />
                        إرسال الملاحظة
                      </Button>
                    </div>
                  </div>
                </div>
              ) : (
                row.status !== "CANCELLED" && <button
                  type="button"
                  data-testid={`respond-${row.id}`}
                  onClick={() => openComposer(row.id)}
                  className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 text-sm font-bold text-white shadow-sm transition hover:-translate-y-0.5 hover:bg-slate-800 sm:w-auto"
                >
                  <MessageSquareReply aria-hidden size={16} />
                  إضافة ملاحظتي
                </button>
              )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

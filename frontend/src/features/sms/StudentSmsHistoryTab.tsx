import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ErrorState } from "@/components/ErrorState";
import { Pagination } from "@/components/Pagination";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey } from "@/features/auth/useMe";
import { getStudentSmsHistory, PROVIDER_LABELS, type AbsenceSmsStatus } from "@/features/sms/api";
import { useActiveSchoolId, useSettingsQuery } from "@/features/settings/hooks";

const STATUS_LABELS: Record<AbsenceSmsStatus, string> = {
  QUEUED: "بانتظار الإرسال",
  SENDING: "جارٍ الإرسال",
  ACCEPTED: "قبله مزود الرسائل",
  FAILED: "تعذر الإرسال",
  UNKNOWN: "نتيجة الإرسال غير مؤكدة",
};

const STATUS_TONES: Record<AbsenceSmsStatus, string> = {
  QUEUED: "bg-slate-100 text-slate-700",
  SENDING: "bg-blue-50 text-blue-800",
  ACCEPTED: "bg-emerald-50 text-emerald-800",
  FAILED: "bg-red-50 text-red-800",
  UNKNOWN: "bg-amber-50 text-amber-900",
};

function formatDateTime(value: string, timezone: string) {
  return new Intl.DateTimeFormat("ar-SA", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(new Date(value));
}

export function StudentSmsHistoryTab({ studentId }: { studentId: number }) {
  const schoolId = useActiveSchoolId();
  const settings = useSettingsQuery();
  const [page, setPage] = useState(1);
  const history = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-sms-history", studentId, page),
    queryFn: ({ signal }) => getStudentSmsHistory(studentId, page, signal),
    enabled: schoolId > 0,
  });

  if (history.isPending) return <Spinner label="جارٍ تحميل رسائل ولي الأمر..." />;
  if (history.isError) return <ErrorState error={history.error} />;

  const timezone = settings.data?.timezone ?? "Asia/Riyadh";
  const rows = history.data.results;
  return (
    <section className="space-y-3" aria-label="رسائل ولي الأمر" data-testid="student-sms-history">
      <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600 shadow-sm">
        <h2 className="font-bold text-slate-900">رسائل الغياب النصية إلى ولي الأمر</h2>
        <p className="mt-1">يعرض السجل جميع الأيام، بغض النظر عن فترة الحضور المختارة. قبول المزود للرسالة لا يؤكد وصولها إلى جوال ولي الأمر.</p>
      </div>
      {rows.length === 0 ? (
        <p className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm">لا توجد رسائل غياب نصية مسجلة لهذا الطالب.</p>
      ) : rows.map((row) => (
        <article key={row.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="font-bold text-slate-900">إشعار غياب يوم {row.attendance_date}</h3>
              <p className="mt-1 text-xs text-slate-600">إلى <bdi>{row.recipient_masked}</bdi> · عبر {PROVIDER_LABELS[row.provider]}</p>
            </div>
            <span className={`rounded-full px-3 py-1 text-xs font-bold ${STATUS_TONES[row.status]}`}>{STATUS_LABELS[row.status]}</span>
          </div>
          {row.message_text ? (
            <div className="mt-3 rounded-xl bg-slate-50 p-3">
              <p className="mb-1 text-xs text-slate-500">نص آخر محاولة مسجلة</p>
              <p className="whitespace-pre-wrap text-sm leading-7 text-slate-800">{row.message_text}</p>
            </div>
          ) : (
            <p className="mt-3 text-xs text-slate-500">لا يوجد نص محفوظ لهذه الرسالة.</p>
          )}
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 border-t border-slate-100 pt-3 text-xs text-slate-600">
            <span>أول طلب إرسال: {formatDateTime(row.requested_at, timezone)}</span>
            {row.attempted_at && <span>آخر محاولة إرسال: {formatDateTime(row.attempted_at, timezone)}</span>}
            {row.accepted_at && <span>قبول المزود: {formatDateTime(row.accepted_at, timezone)}</span>}
            {row.attempts > 1 && <span>عدد المحاولات: {row.attempts}</span>}
          </div>
          {row.status === "UNKNOWN" && <p className="mt-2 text-xs font-bold text-amber-900">تحقق من حساب المزود قبل إعادة الإرسال؛ فقد تكون الرسالة أُرسلت بالفعل.</p>}
        </article>
      ))}
      <Pagination page={page} onChange={setPage} hasNext={Boolean(history.data.next)} hasPrevious={Boolean(history.data.previous)} />
    </section>
  );
}

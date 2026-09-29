import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Send } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Modal } from "@/components/Modal";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/Pagination";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import {
  getAbsenceSmsPreview, PROVIDER_LABELS, sendAbsenceSms,
  type AbsenceSmsCandidate, type AbsenceSmsStatus,
} from "@/features/sms/api";

const STATUS_LABELS: Record<AbsenceSmsStatus, string> = {
  QUEUED: "بانتظار الإرسال",
  SENDING: "جارٍ الإرسال",
  ACCEPTED: "قبله المزود",
  FAILED: "فشل الإرسال؛ يمكن إعادة المحاولة",
  UNKNOWN: "النتيجة غير مؤكدة؛ راجع المزود قبل إعادة الإرسال",
};

const FAILURE_LABELS: Record<string, string> = {
  QUEUE_UNAVAILABLE: "تعذر جدولة الرسالة؛ يمكن إعادة المحاولة.",
  PRE_SEND_STATE_CHANGED: "تغير الغياب أو رقم ولي الأمر قبل الإرسال؛ حدّث القائمة.",
  CREDENTIAL_UNAVAILABLE: "تعذر قراءة مفتاح المزود؛ راجع إعدادات الربط.",
  DREAMS_110: "اسم المستخدم أو مفتاح دريمز غير صحيح.",
  DREAMS_113: "رصيد دريمز غير كافٍ.",
  DREAMS_124: "عنوان خادم المنصة غير مسموح به لدى دريمز.",
};

function todayIso() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Riyadh", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
}

function canSelect(student: AbsenceSmsCandidate) {
  return Boolean(student.recipient_masked)
    && (student.send_status === null || student.send_status === "FAILED");
}

export function AbsenceMessagesPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const schoolId = me.data?.active_school?.id ?? 0;
  const isManager = me.data?.roles.includes("SCHOOL_MANAGER") ?? false;
  const [searchParams] = useSearchParams();
  const initialDate = searchParams.get("date");
  const [date, setDate] = useState(initialDate && /^\d{4}-\d{2}-\d{2}$/.test(initialDate) ? initialDate : todayIso());
  const [page, setPage] = useState(1);
  const contextKey = `${schoolId}:${date}:${page}`;
  const [selection, setSelection] = useState<{ key: string; ids: Set<number> }>(() => ({ key: contextKey, ids: new Set() }));
  const selected = selection.key === contextKey ? selection.ids : new Set<number>();
  const [confirmContext, setConfirmContext] = useState<string | null>(null);
  const confirmOpen = confirmContext === contextKey;
  const [result, setResult] = useState<{ key: string; message: string } | null>(null);
  const preview = useQuery({
    queryKey: schoolScopedKey(schoolId, "sms", "preview", date, page),
    queryFn: ({ signal }) => getAbsenceSmsPreview(date, page, signal),
    enabled: schoolId > 0,
    refetchInterval: (query) => query.state.data?.students.some(
      (student) => student.send_status === "QUEUED" || student.send_status === "SENDING",
    ) ? 5_000 : false,
  });
  const send = useMutation({
    mutationFn: ({ date: targetDate, studentIds }: { date: string; schoolId: number; contextKey: string; studentIds: number[] }) => sendAbsenceSms(targetDate, studentIds),
    onSuccess: (data, variables) => {
      setConfirmContext(null);
      setSelection({ key: variables.contextKey, ids: new Set() });
      setResult({ key: variables.contextKey, message: `أُدرج ${data.queued} مستلم للإرسال، وتجاوز النظام ${data.skipped} مكرر، وتعذر جدولة ${data.queue_failed}.` });
      void queryClient.invalidateQueries({ queryKey: schoolScopedKey(variables.schoolId, "sms", "preview") });
    },
  });

  const data = preview.data;
  const selectable = data?.students.filter(canSelect) ?? [];
  const selectedStudents = data?.students.filter((student) => selected.has(student.student_id)) ?? [];
  const allSelected = selectable.length > 0 && selectable.every((student) => selected.has(student.student_id));

  function toggle(id: number) {
    setSelection((current) => {
      const next = new Set(current.key === contextKey ? current.ids : []);
      if (next.has(id)) next.delete(id); else next.add(id);
      return { key: contextKey, ids: next };
    });
    setResult(null);
  }

  return (
    <div className="ds-page space-y-5" data-testid="absence-messages-page">
      <PageHeader
        icon={Send} eyebrow="الحضور والتشغيل" title="رسائل الغياب"
        description="راجع الغياب غير المعذور بعد اكتمال التحضير، ثم اختر أولياء الأمور المطلوب إشعارهم."
        tone="executive"
        actions={<label className="flex items-center gap-2 rounded-xl bg-white/10 px-3 py-2 text-sm font-bold text-white ring-1 ring-white/15"><CalendarDays aria-hidden size={17} /><span>تاريخ الغياب</span><input type="date" value={date} max={todayIso()} onChange={(event) => { setDate(event.target.value); setPage(1); }} className="rounded-lg border-white/20 bg-white px-2 py-1 text-slate-950" /></label>}
      />
      <Alert title="الإرسال يدوي بعد المراجعة" tone="info">
        تظهر الأيام المصنفة غيابًا كاملًا أو جزئيًا بعد اعتماد جميع حصص الفصل، عندما بقيت حصة غياب بلا عذر. قبول المزود للرسالة لا يثبت وصولها إلى الهاتف.
      </Alert>
      {preview.isPending && <Spinner label="جارٍ إعداد قائمة الغياب..." />}
      {preview.isError && <ErrorState error={preview.error} />}
      {data && (
        <>
          {!data.integration.is_active && (
            <Alert title="لم يُفعّل ربط الرسائل لهذه المدرسة" tone="warning" actions={isManager ? <Link to="/settings?section=sms" className="font-bold text-blue-700 underline">فتح إعدادات الرسائل</Link> : undefined}>
              يجب أن يربط مدير المدرسة حساب دريمز أو مسجات الخاص بها قبل الإرسال.
            </Alert>
          )}
          {data.integration.is_active && <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">المزوّد: {data.integration.provider ? PROVIDER_LABELS[data.integration.provider] : "—"} · اسم المرسل: {data.integration.sender_name}</p>}
          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
              <div>
                <h2 className="font-bold text-slate-900">المستحقون للمراجعة: {data.total}</h2>
                <p className="mt-1 text-xs text-slate-500">الرقم مخفي في العرض، ويُقرأ من سجل الطالب وقت الإرسال.</p>
              </div>
              <label className="flex items-center gap-2 text-sm font-bold text-slate-700">
                <input type="checkbox" checked={allSelected} disabled={!data.integration.is_active || selectable.length === 0} onChange={() => setSelection({ key: contextKey, ids: allSelected ? new Set() : new Set(selectable.map((student) => student.student_id)) })} className="size-5" />
                تحديد المتاح في هذه الصفحة
              </label>
            </div>
            {data.students.length === 0 && <p className="py-8 text-center text-sm text-slate-500">لا توجد حالات غياب مكتملة وغير معذورة في هذا التاريخ.</p>}
            <div className="divide-y divide-slate-100">
              {data.students.map((student) => (
                <label key={student.student_id} className="flex items-start gap-3 py-4">
                  <input
                    type="checkbox" checked={selected.has(student.student_id)}
                    disabled={!data.integration.is_active || !canSelect(student)}
                    onChange={() => toggle(student.student_id)}
                    aria-label={`اختيار ${student.full_name}`} className="mt-1 size-5 shrink-0"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2 text-sm font-bold text-slate-900">
                      {student.full_name}
                      <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-800">{student.absence_status === "FULL" ? "غياب كامل" : "غياب جزئي"}</span>
                    </span>
                    <span className="mt-1 block text-xs text-slate-600">{student.grade_name} · {student.section_name} · ولي الأمر: {student.recipient_masked || "لا يوجد رقم"}</span>
                    <span className="mt-2 block text-xs leading-6 text-slate-500">{student.message}</span>
                    {student.send_status && <span className="mt-1 block text-xs font-bold text-amber-800">{STATUS_LABELS[student.send_status]}{student.send_error && ` · ${FAILURE_LABELS[student.send_error] ?? `رمز الحالة: ${student.send_error}`}`}</span>}
                  </span>
                </label>
              ))}
            </div>
            <Pagination page={page} totalPages={Math.max(1, Math.ceil(data.total / data.page_size))} onChange={setPage} className="mt-5" />
          </section>
          <div className="flex flex-wrap items-center gap-3">
            <Button disabled={!data.integration.is_active || selectedStudents.length === 0} onClick={() => setConfirmContext(contextKey)}>
              <Send aria-hidden size={16} /> مراجعة إرسال {selectedStudents.length} مستلم
            </Button>
            {result?.key === contextKey && <p role="status" className="text-sm font-bold text-emerald-700">{result.message}</p>}
          </div>
        </>
      )}
      {confirmOpen && data && (
        <Modal title="تأكيد رسائل الغياب" description={`ستُرسل رسائل إلى ${selectedStudents.length} ولي أمر عبر حساب هذه المدرسة في ${data.integration.provider ? PROVIDER_LABELS[data.integration.provider] : "المزود"}. قد تُحسب الرسالة العربية على أكثر من جزء لدى المزود.`} onClose={() => { if (!send.isPending) setConfirmContext(null); }}>
          <p className="mb-4 text-sm text-slate-700">تحقق من التاريخ والمستلمين والنصوص المعروضة قبل التأكيد. لن يُعاد إرسال إشعار قَبِله المزود في اليوم نفسه.</p>
          <div className="max-h-48 overflow-y-auto rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
            {selectedStudents.map((student) => <p key={student.student_id} className="py-1">{student.full_name} · {student.recipient_masked}</p>)}
          </div>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button loading={send.isPending} disabled={selectedStudents.length === 0} onClick={() => send.mutate({ date, schoolId, contextKey, studentIds: selectedStudents.map((student) => student.student_id) })}>تأكيد الإرسال</Button>
            <Button variant="secondary" disabled={send.isPending} onClick={() => setConfirmContext(null)}>إلغاء</Button>
          </div>
          {send.isError && <p role="alert" className="mt-3 text-sm text-red-700">{send.error.message}</p>}
        </Modal>
      )}
    </div>
  );
}

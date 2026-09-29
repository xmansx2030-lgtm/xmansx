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
import { patchSettings } from "@/features/settings/api";
import {
  getAbsenceSmsPreview, PROVIDER_LABELS, sendAbsenceSms,
  type AbsenceSmsStatus,
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

const NAME_TOKEN = "«اسم الطالب»";
const DATE_TOKEN = "«التاريخ»";

function validTemplate(value: string) {
  return value.split(NAME_TOKEN).length === 2 && value.split(DATE_TOKEN).length === 2;
}

function SmsTemplateEditor({ schoolId, initial, defaultTemplate }: { schoolId: number; initial: string; defaultTemplate: string }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(initial);
  const [savedDraft, setSavedDraft] = useState(initial);
  const [saved, setSaved] = useState(false);
  const mutation = useMutation({
    mutationFn: () => patchSettings({ absence_sms_message_template: draft.trim() }),
    onSuccess: () => {
      setSavedDraft(draft.trim());
      setSaved(true);
      void queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "sms", "preview") });
    },
  });
  const changed = draft.trim() !== savedDraft;
  return (
    <form onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
      <label htmlFor="absence-sms-template" className="sr-only">نص رسالة الغياب الموحد</label>
      <textarea id="absence-sms-template" rows={3} maxLength={500} value={draft}
        onChange={(event) => { setDraft(event.target.value); setSaved(false); }}
        className="mt-2 block w-full rounded-xl border border-blue-200 bg-white px-4 py-3 text-sm leading-7 text-slate-800"
        dir="rtl" />
      <p className="mt-2 text-xs text-blue-900">أبقِ {NAME_TOKEN} و{DATE_TOKEN} مرة واحدة في الرسالة. يضع النظام الاسم الأول والتاريخ الفعليين عند الإرسال.</p>
      {changed && <p className="mt-1 text-xs font-bold text-amber-800">التعديل غير محفوظ؛ سيُستخدم النص المحفوظ حتى تضغط «حفظ القالب».</p>}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button type="submit" loading={mutation.isPending} disabled={!changed || !validTemplate(draft.trim())}>حفظ القالب لجميع الطلاب</Button>
        <Button type="button" variant="secondary" disabled={draft === defaultTemplate || mutation.isPending}
          onClick={() => { setDraft(defaultTemplate); setSaved(false); }}>استعادة النص الافتراضي</Button>
        {saved && <span role="status" className="text-sm font-bold text-emerald-800">حُفظ القالب لهذه المدرسة.</span>}
      </div>
      {!validTemplate(draft.trim()) && <p role="alert" className="mt-2 text-sm text-red-700">يجب أن يحتوي النص على {NAME_TOKEN} و{DATE_TOKEN} مرة واحدة لكل منهما.</p>}
      {mutation.isError && <p role="alert" className="mt-2 text-sm text-red-700">{mutation.error.message}</p>}
    </form>
  );
}

function todayIso() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Riyadh", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
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
  const contextKey = `${schoolId}:${date}`;
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
    mutationFn: async ({ date: targetDate, studentIds }: { date: string; schoolId: number; contextKey: string; studentIds: number[] }) => {
      const total = { queued: 0, skipped: 0, queue_failed: 0 };
      for (let offset = 0; offset < studentIds.length; offset += 50) {
        const result = await sendAbsenceSms(targetDate, studentIds.slice(offset, offset + 50));
        total.queued += result.queued;
        total.skipped += result.skipped;
        total.queue_failed += result.queue_failed;
      }
      return total;
    },
    onSuccess: (data, variables) => {
      setConfirmContext(null);
      setSelection({ key: variables.contextKey, ids: new Set() });
      setResult({ key: variables.contextKey, message: `أُدرج ${data.queued} مستلم للإرسال، وتجاوز النظام ${data.skipped} مكرر، وتعذر جدولة ${data.queue_failed}.` });
      void queryClient.invalidateQueries({ queryKey: schoolScopedKey(variables.schoolId, "sms", "preview") });
    },
    onError: (_error, variables) => {
      void queryClient.invalidateQueries({ queryKey: schoolScopedKey(variables.schoolId, "sms", "preview") });
    },
  });

  const data = preview.data;
  const candidateIds = data?.candidate_student_ids ?? [];
  const selectedReadyIds = data?.selectable_student_ids.filter((id) => selected.has(id)) ?? [];
  const selectedReadyOnPage = data?.students.filter((student) => selectedReadyIds.includes(student.student_id)) ?? [];
  const selectedCount = candidateIds.filter((id) => selected.has(id)).length;
  const allSelected = candidateIds.length > 0 && candidateIds.every((id) => selected.has(id));

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
        description="راجع الطلاب المصنفين غياب يوم كامل، ثم اختر أولياء الأمور بعد بلوغ معيار التحضير الذي حددته المدرسة."
        tone="executive"
        actions={<label className="flex items-center gap-2 rounded-xl bg-white/10 px-3 py-2 text-sm font-bold text-white ring-1 ring-white/15"><CalendarDays aria-hidden size={17} /><span>تاريخ الغياب</span><input type="date" value={date} max={todayIso()} onChange={(event) => { setDate(event.target.value); setPage(1); }} className="rounded-lg border-white/20 bg-white px-2 py-1 text-slate-950" /></label>}
      />
      <Alert title="الإرسال يدوي بعد المراجعة" tone="info">
        تظهر هنا حالات الغياب الكامل فقط، بما فيها الحالات التي لم تبلغ معيار الإرسال بعد. الرسالة المعروضة معاينة؛ لا يتاح الإرسال إلا بعد بلوغ معيار المدرسة، مع غياب غير معذور ورقم ولي أمر. قبول المزود للرسالة لا يثبت وصولها إلى الهاتف.
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
          <section className="rounded-2xl border border-blue-200 bg-blue-50 p-4 sm:p-5" aria-labelledby="absence-sms-template-title">
            <h2 id="absence-sms-template-title" className="font-bold text-blue-950">قالب رسالة الغياب الكامل</h2>
            {isManager ? <SmsTemplateEditor key={schoolId} schoolId={schoolId} initial={data.message_template} defaultTemplate={data.default_message_template} /> : (
              <p className="mt-2 rounded-xl border border-blue-100 bg-white px-4 py-3 text-sm leading-7 text-slate-800">{data.message_template}</p>
            )}
            <p className="mt-2 text-xs text-blue-900">هذا قالب واحد لجميع الطلاب، ويستخدم الاسم الأول لكل طالب عند الإرسال.</p>
          </section>
          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
              <div>
                <h2 className="font-bold text-slate-900">حالات الغياب الكامل: {data.total} · جاهزون للإرسال: {data.ready_total}</h2>
                <p className="mt-1 text-xs text-slate-500">معيار المدرسة: {data.min_approved_periods === 0 ? "اعتماد جميع حصص التحضير" : `اعتماد ${data.min_approved_periods} من حصص التحضير`} · الرقم مخفي في العرض، ويُقرأ من سجل الطالب وقت الإرسال.</p>
              </div>
              <label className="flex items-center gap-2 text-sm font-bold text-slate-700">
                <input type="checkbox" checked={allSelected} disabled={candidateIds.length === 0} onChange={() => setSelection({ key: contextKey, ids: allSelected ? new Set() : new Set(candidateIds) })} className="size-5" />
                تحديد الكل في جميع الصفحات ({data.total})
              </label>
            </div>
            {data.students.length === 0 && <p className="py-8 text-center text-sm text-slate-500">لا توجد حالات غياب كامل في التحاضير المعتمدة لهذا التاريخ.</p>}
            <div className="divide-y divide-slate-100">
              {data.students.map((student) => (
                <label key={student.student_id} className="flex items-start gap-3 py-4">
                  <input
                    type="checkbox" checked={selected.has(student.student_id)}
                    onChange={() => toggle(student.student_id)}
                    aria-label={`اختيار ${student.full_name}`} className="mt-1 size-5 shrink-0"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2 text-sm font-bold text-slate-900">
                      {student.full_name}
                      <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-800">{student.submitted_periods < student.expected_periods ? "غائب في جميع التحاضير المعتمدة" : "غياب يوم كامل"}</span>
                    </span>
                    <span className="mt-1 block text-xs text-slate-600">{student.grade_name} · {student.section_name} · التحاضير المعتمدة: {student.submitted_periods} من {student.expected_periods} · ولي الأمر: {student.recipient_masked || "لا يوجد رقم"}</span>
                    {student.eligibility_reason && <span className="mt-1 block text-xs font-bold text-amber-800">{student.eligibility_reason === "INSUFFICIENT_APPROVALS" ? `بانتظار اعتماد ${student.required_periods} من حصص التحضير حسب معيار المدرسة.` : student.eligibility_reason === "EXCUSED_ABSENCE" ? "الغياب مغطى بعذر؛ لا تُرسل رسالة غياب غير معذور." : "أضف رقم جوال ولي الأمر قبل الإرسال."}</span>}
                    {student.send_status && <span className="mt-1 block text-xs font-bold text-amber-800">{STATUS_LABELS[student.send_status]}{student.send_error && ` · ${FAILURE_LABELS[student.send_error] ?? `رمز الحالة: ${student.send_error}`}`}</span>}
                  </span>
                </label>
              ))}
            </div>
            <Pagination page={page} totalPages={Math.max(1, Math.ceil(data.total / data.page_size))} onChange={setPage} className="mt-5" />
          </section>
          <div className="flex flex-wrap items-center gap-3">
            <Button disabled={!data.integration.is_active || selectedReadyIds.length === 0} onClick={() => setConfirmContext(contextKey)}>
              <Send aria-hidden size={16} /> مراجعة إرسال {selectedReadyIds.length} من {selectedCount} محدد
            </Button>
            {selectedCount > selectedReadyIds.length && <p className="text-sm text-amber-800">{selectedCount - selectedReadyIds.length} من المحددين غير جاهز للإرسال حاليًا حسب معيار المدرسة أو حالة الغياب أو رقم ولي الأمر.</p>}
            {result?.key === contextKey && <p role="status" className="text-sm font-bold text-emerald-700">{result.message}</p>}
            {send.isError && <p role="alert" className="text-sm text-red-700">تعذر إكمال إرسال كل الدفعات. حدّث القائمة وراجع الحالات قبل إعادة المحاولة. {send.error.message}</p>}
          </div>
        </>
      )}
      {confirmOpen && data && (
        <Modal title="تأكيد رسائل الغياب" description={`ستُرسل رسائل إلى ${selectedReadyIds.length} ولي أمر عبر حساب هذه المدرسة في ${data.integration.provider ? PROVIDER_LABELS[data.integration.provider] : "المزود"}. قد تُحسب الرسالة العربية على أكثر من جزء لدى المزود.`} onClose={() => { if (!send.isPending) setConfirmContext(null); }}>
          <p className="mb-3 text-sm text-slate-700">سيستخدم النظام القالب المحفوظ التالي، مع إدراج الاسم الأول لكل طالب وتاريخ الغياب تلقائيًا. لن يُعاد إرسال إشعار قَبِله المزود في اليوم نفسه.</p>
          <p className="mb-4 rounded-xl border border-blue-100 bg-blue-50 p-3 text-sm leading-7 text-slate-800">{data.message_template}</p>
          <div className="max-h-48 overflow-y-auto rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
            {selectedReadyOnPage.map((student) => <p key={student.student_id} className="py-1">{student.full_name} · {student.recipient_masked}</p>)}
            {selectedReadyIds.length > selectedReadyOnPage.length && <p className="py-1">و{selectedReadyIds.length - selectedReadyOnPage.length} مستلم من الصفحات الأخرى.</p>}
          </div>
          {selectedCount > selectedReadyIds.length && <p className="mt-2 text-sm font-bold text-amber-800">لن تُرسل رسائل إلى {selectedCount - selectedReadyIds.length} من المحددين غير الجاهزين حاليًا.</p>}
          <div className="mt-5 flex flex-wrap gap-3">
            <Button loading={send.isPending} disabled={selectedReadyIds.length === 0} onClick={() => send.mutate({ date, schoolId, contextKey, studentIds: selectedReadyIds })}>تأكيد الإرسال</Button>
            <Button variant="secondary" disabled={send.isPending} onClick={() => setConfirmContext(null)}>إلغاء</Button>
          </div>
          {send.isError && <p role="alert" className="mt-3 text-sm text-red-700">{send.error.message}</p>}
        </Modal>
      )}
    </div>
  );
}

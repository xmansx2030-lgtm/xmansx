import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Send } from "lucide-react";
import { useRef, useState } from "react";
import { adaptivePollingInterval, POLLING } from "@/app/polling";
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
  UNKNOWN: "لم نتأكد من إرسال الرسالة",
};

const FAILURE_LABELS: Record<string, string> = {
  QUEUE_UNAVAILABLE: "تعذر جدولة الرسالة؛ يمكن إعادة المحاولة.",
  PRE_SEND_STATE_CHANGED: "تغير الغياب أو رقم ولي الأمر قبل الإرسال؛ حدّث القائمة.",
  CREDENTIAL_UNAVAILABLE: "تعذر قراءة مفتاح المزود؛ راجع إعدادات الربط.",
  DREAMS_RESPONSE_UNKNOWN: "تحقق من «الرسائل المرسلة» في حساب دريمز قبل إعادة إرسالها؛ فقد تكون أُرسلت بالفعل.",
  DREAMS_110: "اسم المستخدم أو مفتاح دريمز غير صحيح.",
  DREAMS_113: "رصيد دريمز غير كافٍ.",
  DREAMS_124: "عنوان خادم المنصة غير مسموح به لدى دريمز.",
};

const NAME_TOKEN = "«اسم الطالب»";
const DATE_TOKEN = "«التاريخ»";

function validTemplate(value: string) {
  return value.split(NAME_TOKEN).length === 2 && value.split(DATE_TOKEN).length === 2;
}

function tokenCount(value: string, token: string) {
  return value.split(token).length - 1;
}

function SmsTemplateEditor({ schoolId, schoolType, date, initial, defaultTemplate }: { schoolId: number; schoolType: string; date: string; initial: string; defaultTemplate: string }) {
  const queryClient = useQueryClient();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
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
  const nameCount = tokenCount(draft, NAME_TOKEN);
  const dateCount = tokenCount(draft, DATE_TOKEN);
  const sample = validTemplate(draft.trim())
    ? draft.trim().replace(NAME_TOKEN, schoolType === "GIRLS" ? "سارة" : "أحمد").replace(DATE_TOKEN, date)
    : null;

  function insertToken(token: string) {
    const textarea = textareaRef.current;
    if (!textarea || tokenCount(draft, token) > 0) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    if (draft.length - (end - start) + token.length > 500) return;
    const nextDraft = `${draft.slice(0, start)}${token}${draft.slice(end)}`;
    setDraft(nextDraft);
    setSaved(false);
    mutation.reset();
    requestAnimationFrame(() => {
      textarea.focus();
      const caret = start + token.length;
      textarea.setSelectionRange(caret, caret);
    });
  }

  return (
    <form onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }} className="mt-4 space-y-4">
      <div>
        <label htmlFor="absence-sms-template" className="mb-1.5 block text-sm font-bold text-slate-800">نص رسالة الغياب الموحد</label>
        <p id="absence-sms-template-help" className="mb-2 text-xs leading-5 text-slate-600">
          اكتب رسالة واضحة ومختصرة؛ يُستبدل كل رمز مرة واحدة بالاسم الأول والتاريخ عند الإرسال.
        </p>
        <textarea
          ref={textareaRef}
          id="absence-sms-template"
          aria-describedby="absence-sms-template-help absence-sms-template-count"
          rows={4}
          maxLength={500}
          value={draft}
          disabled={mutation.isPending}
          onChange={(event) => { setDraft(event.target.value); setSaved(false); mutation.reset(); }}
          className="block min-h-28 w-full resize-y rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm leading-7 text-slate-800 shadow-sm outline-none transition focus:border-teal-700 focus:ring-2 focus:ring-teal-700/15"
          dir="rtl"
        />
        <div className="mt-1 flex items-center justify-between gap-3 text-xs text-slate-600">
          <span>حتى ٥٠٠ حرف</span>
          <span id="absence-sms-template-count" aria-live="polite" className={draft.length >= 480 ? "font-bold text-amber-800" : ""}>{draft.length} / 500</span>
        </div>
      </div>

      <div className="rounded-xl border border-teal-100 bg-white/80 p-3">
        <p className="text-sm font-bold text-slate-800">إضافة رمز إلى موضع المؤشر</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <button type="button" onClick={() => insertToken(NAME_TOKEN)} disabled={nameCount > 0 || mutation.isPending}
            className="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-sm font-semibold text-teal-900 transition hover:bg-teal-100 focus:outline-none focus:ring-2 focus:ring-teal-700 disabled:cursor-not-allowed disabled:opacity-60">
            {NAME_TOKEN} {nameCount > 0 ? "— مضاف" : "— إضافة"}
          </button>
          <button type="button" onClick={() => insertToken(DATE_TOKEN)} disabled={dateCount > 0 || mutation.isPending}
            className="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-sm font-semibold text-teal-900 transition hover:bg-teal-100 focus:outline-none focus:ring-2 focus:ring-teal-700 disabled:cursor-not-allowed disabled:opacity-60">
            {DATE_TOKEN} {dateCount > 0 ? "— مضاف" : "— إضافة"}
          </button>
        </div>
        <p className="mt-2 text-xs leading-5 text-slate-600">يجب أن يظهر كل رمز مرة واحدة فقط. انقر داخل النص أولًا لاختيار موضع الإدراج.</p>
      </div>

      <div className="rounded-xl border border-slate-200 bg-[#f7f9f7] p-3" aria-live="polite">
        <p className="text-xs font-bold uppercase tracking-wide text-slate-600">معاينة رسالة نموذجية</p>
        {sample ? (
          <p className="mt-2 rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm leading-7 text-slate-800">{sample}</p>
        ) : (
          <p className="mt-2 text-sm leading-6 text-amber-800">أكمل رمزي الاسم والتاريخ مرة واحدة لعرض المعاينة.</p>
        )}
      </div>

      {changed && <p role="status" className="rounded-lg bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-900">التعديل غير محفوظ؛ سيُستخدم النص المحفوظ حتى تضغط «حفظ القالب».</p>}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" loading={mutation.isPending} disabled={!changed || !validTemplate(draft.trim())}>حفظ القالب لجميع الطلاب</Button>
        <Button type="button" variant="secondary" disabled={draft === defaultTemplate || mutation.isPending}
          onClick={() => { setDraft(defaultTemplate); setSaved(false); mutation.reset(); }}>استعادة النص الافتراضي</Button>
        {saved && <span role="status" className="text-sm font-bold text-teal-800">حُفظ القالب لهذه المدرسة.</span>}
      </div>
      {!validTemplate(draft.trim()) && (
        <p role="alert" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          يجب أن يحتوي النص على {NAME_TOKEN} و{DATE_TOKEN} مرة واحدة لكل منهما.
          {nameCount > 1 && " رمز الاسم مكرر."}{dateCount > 1 && " رمز التاريخ مكرر."}
        </p>
      )}
      {mutation.isError && <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{mutation.error.message}</p>}
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
    ) ? adaptivePollingInterval(POLLING.jobStatus)(query) : false,
    refetchIntervalInBackground: false,
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
  const contactIssues = data?.contact_issues ?? [];
  const missingContacts = contactIssues.filter((issue) => issue.reason === "MISSING_RECIPIENT");
  const invalidContacts = contactIssues.filter((issue) => issue.reason === "INVALID_RECIPIENT");
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
        description="راجع الغائبين في جميع التحاضير المعتمدة لفصلهم حتى الآن، ثم اختر أولياء الأمور لإرسال التنبيه."
        tone="executive"
        actions={<label className="flex items-center gap-2 rounded-xl bg-white/10 px-3 py-2 text-sm font-bold text-white ring-1 ring-white/15"><CalendarDays aria-hidden size={17} /><span>تاريخ الغياب</span><input type="date" value={date} max={todayIso()} onChange={(event) => { setDate(event.target.value); setPage(1); }} className="rounded-lg border-white/20 bg-white px-2 py-1 text-slate-950" /></label>}
      />
      <Alert title="الإرسال يدوي بعد المراجعة" tone="info">
        يعتمد الإرسال على غياب الطالب في جميع التحاضير المعتمدة لفصله حتى الآن، ولو اعتمد فصل آخر عددًا مختلفًا من الحصص. لا ينتظر النظام اكتمال جدول اليوم، وقد تتغير حالة الغياب عند اعتماد تحضير لاحق. يُستبعد الغياب المعذور والطلاب بلا رقم ولي أمر صالح. قبول المزود للرسالة لا يثبت وصولها إلى الهاتف.
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
          {contactIssues.length > 0 && (
            <Alert title="تنبيه: بيانات جوال ولي الأمر تحتاج تصحيحًا" tone="warning" actions={isManager ? <Link to="/students" className="font-bold text-amber-950 underline">فتح قائمة الطلاب لتصحيح الأرقام</Link> : undefined}>
              <p>حالات الغياب الكامل لهذا التاريخ: بلا رقم {missingContacts.length} · رقم بصيغة غير صحيحة {invalidContacts.length}. تظهر الأسماء من جميع الصفحات، ولن تُرسل لهم رسالة حتى تصحيح الرقم.</p>
              <ul className="mt-3 max-h-60 space-y-2 overflow-y-auto rounded-xl bg-white/70 p-3">
                {contactIssues.map((issue) => (
                  <li key={issue.student_id} className="flex flex-wrap items-baseline justify-between gap-x-3 border-b border-amber-100 pb-2 last:border-0 last:pb-0">
                    <span className="font-bold">{issue.full_name} · {issue.grade_name} / {issue.section_name}</span>
                    <span>{issue.reason === "MISSING_RECIPIENT" ? "لا يوجد رقم" : "الرقم المسجل بصيغة غير صحيحة"}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs">فحص الصيغة لا يؤكد أن الرقم يعمل أو يخص ولي الأمر.</p>
              {!isManager && <p className="mt-2 text-xs">يمكن لمدير المدرسة تصحيح الأرقام من قائمة الطلاب.</p>}
            </Alert>
          )}
          <section className="rounded-2xl border border-teal-200 bg-[#eff7f3] p-4 sm:p-5" aria-labelledby="absence-sms-template-title">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="text-xs font-bold tracking-wide text-teal-800">إعدادات المدرسة</p>
                <h2 id="absence-sms-template-title" className="mt-1 font-bold text-slate-950">قالب رسالة الغياب الكامل</h2>
              </div>
              {isManager && <span className="rounded-full bg-white px-3 py-1 text-xs font-bold text-teal-900 ring-1 ring-teal-200">يُطبق على جميع الطلاب</span>}
            </div>
            {isManager ? <SmsTemplateEditor key={schoolId} schoolId={schoolId} schoolType={me.data?.active_school?.school_type ?? "BOYS"} date={date} initial={data.message_template} defaultTemplate={data.default_message_template} /> : (
              <p className="mt-3 rounded-xl border border-teal-100 bg-white px-4 py-3 text-sm leading-7 text-slate-800">{data.message_template}</p>
            )}
            <p className="mt-3 text-xs leading-5 text-teal-950">هذا قالب واحد لجميع الطلاب، ويستخدم الاسم الأول لكل طالب عند الإرسال.</p>
          </section>
          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
              <div>
                <h2 className="font-bold text-slate-900">الغائبون في جميع التحاضير المعتمدة: {data.total} · جاهزون للإرسال: {data.ready_total}</h2>
                <p className="mt-1 text-xs text-slate-500">يُحتسب الغياب لكل فصل من تحاضيره المعتمدة حتى الآن، بغض النظر عن عدد تحاضير الفصول الأخرى. الرقم مخفي في العرض، ويُقرأ من سجل الطالب وقت الإرسال.</p>
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
                    {student.eligibility_reason && <span className="mt-1 block text-xs font-bold text-amber-800">{student.eligibility_reason === "NO_APPROVED_ATTENDANCE" ? "لم يُعتمد تحضير لهذا الطالب بعد." : student.eligibility_reason === "EXCUSED_ABSENCE" ? "الغياب مغطى بعذر؛ لا تُرسل رسالة غياب غير معذور." : student.eligibility_reason === "INVALID_RECIPIENT" ? "صحح صيغة رقم جوال ولي الأمر قبل الإرسال." : "أضف رقم جوال ولي الأمر قبل الإرسال."}</span>}
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
            {selectedCount > selectedReadyIds.length && <p className="text-sm text-amber-800">{selectedCount - selectedReadyIds.length} من المحددين لن تُرسل لهم رسالة بسبب عذر مقبول أو رقم ولي أمر غير صالح أو عدم وجود تحضير معتمد أو إشعار إرسال سابق.</p>}
            {result?.key === contextKey && <p role="status" className="text-sm font-bold text-emerald-700">{result.message}</p>}
            {send.isError && <p role="alert" className="text-sm text-red-700">تعذر إكمال إرسال كل الدفعات. حدّث القائمة وراجع الحالات قبل إعادة المحاولة. {send.error.message}</p>}
          </div>
        </>
      )}
      {confirmOpen && data && (
        <Modal title="تأكيد رسائل الغياب" description={`ستُرسل رسائل إلى ${selectedReadyIds.length} ولي أمر عبر حساب هذه المدرسة في ${data.integration.provider ? PROVIDER_LABELS[data.integration.provider] : "المزود"}. قد تُحسب الرسالة العربية على أكثر من جزء لدى المزود.`} onClose={() => { if (!send.isPending) setConfirmContext(null); }}>
          <p className="mb-3 text-sm text-slate-700">سيستخدم النظام القالب المحفوظ التالي، مع إدراج الاسم الأول لكل طالب وتاريخ الغياب تلقائيًا. يستند الغياب إلى التحاضير المعتمدة حتى الآن وقد تتغير حالته لاحقًا. لن يُعاد إرسال إشعار قَبِله المزود في اليوم نفسه.</p>
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

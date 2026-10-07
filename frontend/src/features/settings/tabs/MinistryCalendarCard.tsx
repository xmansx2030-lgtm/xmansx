import { CalendarCheck2, ExternalLink, ShieldCheck } from "lucide-react";

import type { MinistryCalendarStatus } from "@/features/settings/api";

const dateFormat = new Intl.DateTimeFormat("ar-SA-u-ca-gregory", {
  day: "numeric", month: "long", year: "numeric", timeZone: "Asia/Riyadh",
});
const LABELS: Record<string, string> = {
  year_start: "بداية العام الدراسي",
  year_end: "نهاية العام الدراسي",
  semester_1_start: "بداية الفصل الأول",
  semester_1_end: "نهاية الفصل الأول",
  semester_2_start: "بداية الفصل الثاني",
  semester_2_end: "نهاية الفصل الثاني",
};
const OUTCOMES: Record<string, string> = {
  APPLIED: "التقويم الرسمي مطبق، والتفعيل يعمل تلقائيًا.",
  ENROLLMENTS_NOT_READY: "العام الرسمي جاهز. ينتظر التفعيل اكتمال قيود الطلاب في العام الجديد من ملف نور.",
  DAY_ALREADY_IN_USE: "بدأ تحضير اليوم في العام السابق. يُؤجل الانتقال إلى اليوم التالي لحفظ هذه التحاضير.",
  CALENDAR_EXISTING_DATES_CONFLICT: "مواعيد التقويم القائم تختلف عن المصدر. يلزم أن تراجعها إدارة المنصة قبل الانتقال.",
  CALENDAR_YEAR_CONFLICT: "يوجد أكثر من عام بتاريخ البداية نفسه؛ يلزم مراجعة إدارة المنصة.",
  SOURCE_INCOMPLETE: "بيانات المصدر غير مكتملة؛ يستمر التقويم القائم حتى اكتمالها.",
  SOURCE_INVALID: "توجد تواريخ متعارضة في المصدر؛ أُوقف الانتقال التلقائي لحين التحقق.",
  BETWEEN_SEMESTERS: "إجازة بين الفصلين. يبدأ تفعيل الفصل التالي في موعده المحدد.",
  BETWEEN_ACADEMIC_YEARS: "انتهت مدة الدراسة. يستمر حفظ القيود حتى تجهيز العام التالي.",
};

export function MinistryCalendarCard({ data }: { data: MinistryCalendarStatus }) {
  const calendar = data.current_calendar;
  const message = data.profile === "UNCONFIRMED"
    ? "تحدد إدارة المنصة نطاق المدرسة مرة واحدة، ثم تعمل المزامنة دون إدخال المواعيد سنويًا."
    : data.profile === "EXCEPTION"
      ? "لهذه المدرسة تقويم خاص معتمد؛ لا يُطبّق عليها التقويم الوطني تلقائيًا."
      : OUTCOMES[data.outcome] ?? "المزامنة الرسمية مفعلة؛ ينتظر تطبيق التقويم التحقق من جاهزيته.";
  return (
    <section aria-label="مصدر التقويم الدراسي" className="rounded-3xl border border-teal-200 bg-gradient-to-l from-teal-50 via-white to-blue-50 p-5 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-xs font-black text-teal-700"><ShieldCheck aria-hidden size={16} /> مصدر موثق وقواعد واضحة</p>
          <h3 className="mt-2 text-lg font-black text-slate-950">التقويم من وزارة التعليم</h3>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{message}</p>
        </div>
        <a href={data.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-teal-200 bg-white px-4 text-sm font-bold text-teal-800">
          الموقع الرسمي <ExternalLink aria-hidden size={16} />
        </a>
      </div>
      {data.error_code && (
        <p role="alert" className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          {data.error_code === "NOT_SYNCED" ? "لم تُجرَ المزامنة الأولى بعد." : "تعذر تحديث المصدر الرسمي. تُعرض آخر بيانات ناجحة ويتوقف الانتقال التلقائي حتى استعادة المزامنة."}
        </p>
      )}
      {data.automatic_enabled === false && <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">المزامنة والتفعيل التلقائي موقوفان حاليًا من إدارة المنصة.</p>}
      {calendar && (
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(LABELS).map(([key, label]) => {
            const value = calendar.dates[key];
            const evidence = calendar.evidence[key];
            return (
              <article key={key} className="rounded-2xl border border-slate-200/70 bg-white/90 p-4">
                <p className="text-xs font-bold text-slate-500">{label}</p>
                <p className="mt-2 font-black text-slate-950">{value ? dateFormat.format(new Date(`${value}T12:00:00+03:00`)) : "لم يُحدد من المصدر"}</p>
                {evidence && <p className="mt-2 text-xs leading-5 text-slate-500">
                  {evidence.basis === "CALCULATED"
                    ? key === "semester_2_start" ? "محسوب: بداية إجازة منتصف العام + 9 أيام" : "حد الفصل: اليوم السابق لإجازة منتصف العام"
                    : evidence.basis === "YEAR_BOUNDARY" ? "مطابق لحد العام الدراسي" : "تاريخ منشور من الوزارة"}
                </p>}
                {evidence && <a href={evidence.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex min-h-8 items-center gap-1 text-xs font-bold text-teal-700">مصدر التاريخ <ExternalLink aria-hidden size={12} /></a>}
              </article>
            );
          })}
        </div>
      )}
      {calendar?.status === "INCOMPLETE" && <p className="mt-4 text-sm font-bold text-amber-800">بانتظار اكتمال: {calendar.missing.map((key) => LABELS[key] ?? key).join("، ")}.</p>}
      {calendar?.status === "INVALID" && <p role="alert" className="mt-4 text-sm font-bold text-red-800">تعذر اعتماد التواريخ لوجود تعارض أو اختلاف في نظام الفصول.</p>}
      <p className="mt-4 flex items-center gap-2 text-xs text-slate-500"><CalendarCheck2 aria-hidden size={15} /> آخر مزامنة ناجحة: {data.succeeded_at ? new Intl.DateTimeFormat("ar-SA-u-ca-gregory", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Riyadh" }).format(new Date(data.succeeded_at)) : "لم تتم بعد"}</p>
    </section>
  );
}

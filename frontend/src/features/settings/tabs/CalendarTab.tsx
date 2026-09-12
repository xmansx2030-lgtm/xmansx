import { useMutation } from "@tanstack/react-query";
import {
  Archive,
  CalendarCheck2,
  CalendarClock,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Pencil,
  Plus,
  Power,
  Sparkles,
} from "lucide-react";
import { useState, type ButtonHTMLAttributes, type FormEvent, type ReactNode } from "react";

import { ApiError } from "@/api/client";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Modal } from "@/components/Modal";
import { Spinner } from "@/components/Spinner";
import { TextField } from "@/components/TextField";
import {
  activateSemester,
  createSemester,
  createYear,
  updateSemester,
  updateYear,
  yearAction,
  type AcademicYear,
  type Semester,
} from "@/features/settings/api";
import { useInvalidateSchoolData, useYearsQuery } from "@/features/settings/hooks";

type YearFormValue = {
  name: string;
  start_date: string;
  end_date: string;
  activate: boolean;
};

type SemesterFormValue = {
  name: string;
  sequence: number;
  start_date: string;
  end_date: string;
  activate: boolean;
};

type CalendarEditor =
  | { kind: "create-year" }
  | { kind: "edit-year"; year: AcademicYear }
  | { kind: "create-semester"; year: AcademicYear }
  | { kind: "edit-semester"; year: AcademicYear; semester: Semester }
  | null;

type CalendarConfirmation =
  | { kind: "activate-year"; year: AcademicYear }
  | { kind: "close-year"; year: AcademicYear }
  | { kind: "archive-year"; year: AcademicYear }
  | { kind: "activate-semester"; year: AcademicYear; semester: Semester }
  | null;

type SaveRequest =
  | { kind: "create-year"; data: YearFormValue }
  | { kind: "edit-year"; year: AcademicYear; data: YearFormValue }
  | { kind: "create-semester"; year: AcademicYear; data: SemesterFormValue }
  | { kind: "edit-semester"; semester: Semester; data: SemesterFormValue };

type CalendarStatus = AcademicYear["status"] | Semester["status"];

const STATUS_META = {
  UPCOMING: { label: "قادم", tone: "info" },
  ACTIVE: { label: "نشط الآن", tone: "success" },
  CLOSED: { label: "منتهي", tone: "neutral" },
  ARCHIVED: { label: "مؤرشف", tone: "violet" },
} as const;

const arabicDateFormatter = new Intl.DateTimeFormat("ar-SA-u-ca-gregory", {
  day: "numeric",
  month: "long",
  year: "numeric",
});
const arabicNumberFormatter = new Intl.NumberFormat("ar-SA");
const DAY_IN_MS = 86_400_000;

export function CalendarTab({ canWrite }: { canWrite: boolean }) {
  const years = useYearsQuery();
  const invalidate = useInvalidateSchoolData();
  const [editor, setEditor] = useState<CalendarEditor>(null);
  const [confirmation, setConfirmation] = useState<CalendarConfirmation>(null);
  const [showAllUpcoming, setShowAllUpcoming] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = () => invalidate("academic-years");

  const saveMutation = useMutation({
    mutationFn: async (request: SaveRequest) => {
      if (request.kind === "create-year") {
        const created = await createYear(request.data);
        return request.data.activate
          ? `تم إنشاء العام «${created.name}» وتفعيله في خطوة واحدة.`
          : `تم حفظ العام «${created.name}» كعام قادم دون تغيير التشغيل الحالي.`;
      }
      if (request.kind === "edit-year") {
        const data = {
          name: request.data.name,
          start_date: request.data.start_date,
          end_date: request.data.end_date,
        };
        const updated = await updateYear(request.year.id, data);
        return `تم حفظ تعديلات العام «${updated.name}».`;
      }
      if (request.kind === "create-semester") {
        const created = await createSemester(request.year.id, request.data);
        return request.data.activate
          ? `تم إنشاء الفصل «${created.name}» وتفعيله في خطوة واحدة.`
          : `تمت إضافة الفصل «${created.name}» كفصل قادم.`;
      }
      const data = {
        name: request.data.name,
        sequence: request.data.sequence,
        start_date: request.data.start_date,
        end_date: request.data.end_date,
      };
      const updated = await updateSemester(request.semester.id, data);
      return `تم حفظ تعديلات الفصل «${updated.name}».`;
    },
    onSuccess: async (message) => {
      setError(null);
      setNotice(message);
      setEditor(null);
      await refresh();
    },
    onError: (caught) => setError(apiMessage(caught, "تعذر حفظ التغييرات.")),
  });

  const actionMutation = useMutation({
    mutationFn: async (action: NonNullable<CalendarConfirmation>) => {
      if (action.kind === "activate-semester") {
        await activateSemester(action.semester.id);
        return `تم تفعيل الفصل «${action.semester.name}».`;
      }
      const actionName = action.kind.replace("-year", "") as "activate" | "close" | "archive";
      await yearAction(action.year.id, actionName);
      if (action.kind === "activate-year") return `تم تفعيل العام «${action.year.name}».`;
      if (action.kind === "close-year") return `تم إغلاق العام «${action.year.name}» وحفظ سجله.`;
      return `تمت أرشفة العام «${action.year.name}».`;
    },
    onSuccess: async (message) => {
      setError(null);
      setNotice(message);
      setConfirmation(null);
      await refresh();
    },
    onError: (caught) => setError(apiMessage(caught, "تعذر تنفيذ الإجراء.")),
  });

  if (years.isPending) return <Spinner />;
  if (years.isError) return <ErrorState error={years.error} />;

  const activeYear = years.data.find((year) => year.status === "ACTIVE");
  const activeSemester = activeYear?.semesters.find((semester) => semester.status === "ACTIVE");
  const currentYears = years.data
    .filter((year) => year.status === "ACTIVE" || year.status === "UPCOMING")
    .sort((a, b) => {
      if (a.status !== b.status) return a.status === "ACTIVE" ? -1 : 1;
      return a.status === "UPCOMING"
        ? a.start_date.localeCompare(b.start_date)
        : b.start_date.localeCompare(a.start_date);
    });
  const historyYears = years.data.filter(
    (year) => year.status === "CLOSED" || year.status === "ARCHIVED",
  ).sort((a, b) => b.start_date.localeCompare(a.start_date));
  const visibleCurrentYears = showAllUpcoming
    ? currentYears
    : currentYears.filter((year, index) => year.status === "ACTIVE" || index < 4);
  const hiddenUpcomingCount = currentYears.length - visibleCurrentYears.length;
  const upcomingCount = years.data.filter((year) => year.status === "UPCOMING").length;
  const totalSemesters = years.data.reduce((total, year) => total + year.semesters.length, 0);
  const busy = saveMutation.isPending || actionMutation.isPending;

  const openEditor = (next: NonNullable<CalendarEditor>) => {
    saveMutation.reset();
    setError(null);
    setNotice(null);
    setEditor(next);
  };
  const openConfirmation = (next: NonNullable<CalendarConfirmation>) => {
    actionMutation.reset();
    setError(null);
    setNotice(null);
    setConfirmation(next);
  };

  return (
    <div className="space-y-6" data-testid="academic-calendar-tab">
      <CalendarOverview
        activeYear={activeYear}
        activeSemester={activeSemester}
        upcomingCount={upcomingCount}
        totalSemesters={totalSemesters}
        canWrite={canWrite}
        onCreateYear={() => openEditor({ kind: "create-year" })}
      />

      {error && !editor && !confirmation && (
        <div
          role="alert"
          className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm font-bold text-red-800"
        >
          {error}
        </div>
      )}
      {notice && (
        <div
          role="status"
          className="flex items-start gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-bold text-emerald-900"
        >
          <CheckCircle2 aria-hidden size={18} className="mt-0.5 shrink-0" />
          <span>{notice}</span>
        </div>
      )}

      <section aria-labelledby="calendar-years-heading">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs font-black text-blue-700">الخطة الدراسية</p>
            <h3 id="calendar-years-heading" className="mt-1 text-lg font-black text-slate-950">
              الأعوام الحالية والقادمة
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              عدّل المواعيد وجهّز الفصول قبل اعتمادها للتشغيل.
            </p>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600">
            {formatNumber(years.data.length)} عام · {formatNumber(totalSemesters)} فصل
          </span>
        </div>

        <div className="space-y-4" data-testid="calendar-primary-years">
          {visibleCurrentYears.map((year) => (
            <YearCard
              key={year.id}
              year={year}
              activeYear={activeYear}
              canWrite={canWrite}
              busy={busy}
              onEdit={() => openEditor({ kind: "edit-year", year })}
              onAddSemester={() => openEditor({ kind: "create-semester", year })}
              onEditSemester={(semester) =>
                openEditor({ kind: "edit-semester", year, semester })
              }
              onAction={(next) => openConfirmation(next)}
            />
          ))}
          {currentYears.length === 0 && (
            <EmptyCalendar canWrite={canWrite} onCreate={() => openEditor({ kind: "create-year" })} />
          )}
          {hiddenUpcomingCount > 0 && (
            <button
              type="button"
              className="min-h-11 w-full rounded-2xl border border-dashed border-blue-200 bg-blue-50 px-4 text-sm font-black text-blue-800 transition hover:border-blue-300 hover:bg-blue-100"
              onClick={() => setShowAllUpcoming(true)}
            >
              عرض {formatNumber(hiddenUpcomingCount)} أعوام قادمة إضافية
            </button>
          )}
          {showAllUpcoming && currentYears.filter((year) => year.status === "UPCOMING").length > 3 && (
            <button
              type="button"
              className="min-h-11 w-full rounded-2xl border border-slate-200 bg-white px-4 text-sm font-bold text-slate-600 transition hover:bg-slate-50"
              onClick={() => setShowAllUpcoming(false)}
            >
              اختصار قائمة الأعوام القادمة
            </button>
          )}
        </div>
      </section>

      {historyYears.length > 0 && (
        <section className="rounded-2xl border border-slate-200 bg-slate-50/70 p-3 sm:p-4">
          <button
            type="button"
            className="flex min-h-11 w-full items-center justify-between gap-3 rounded-xl px-2 text-start text-sm font-black text-slate-700 transition hover:bg-white"
            aria-expanded={showHistory}
            aria-controls="academic-calendar-history"
            onClick={() => setShowHistory((value) => !value)}
          >
            <span className="inline-flex items-center gap-2">
              <Archive aria-hidden size={17} className="text-slate-500" />
              السجل السابق والمؤرشف
            </span>
            <span className="rounded-full bg-white px-2.5 py-1 text-xs text-slate-500 shadow-sm">
              {formatNumber(historyYears.length)}
            </span>
          </button>
          {showHistory && (
            <div id="academic-calendar-history" className="mt-3 space-y-3">
              {historyYears.map((year) => (
                <YearCard
                  key={year.id}
                  year={year}
                  activeYear={activeYear}
                  canWrite={canWrite}
                  busy={busy}
                  onEdit={() => openEditor({ kind: "edit-year", year })}
                  onAddSemester={() => openEditor({ kind: "create-semester", year })}
                  onEditSemester={(semester) =>
                    openEditor({ kind: "edit-semester", year, semester })
                  }
                  onAction={(next) => openConfirmation(next)}
                />
              ))}
            </div>
          )}
        </section>
      )}

      {editor?.kind === "create-year" && (
        <YearFormModal
          key="create-year"
          years={years.data}
          activeYear={activeYear}
          pending={saveMutation.isPending}
          error={error}
          onClose={() => !saveMutation.isPending && setEditor(null)}
          onSave={(data) => saveMutation.mutate({ kind: "create-year", data })}
        />
      )}
      {editor?.kind === "edit-year" && (
        <YearFormModal
          key={`edit-year-${editor.year.id}`}
          year={editor.year}
          years={years.data}
          activeYear={activeYear}
          pending={saveMutation.isPending}
          error={error}
          onClose={() => !saveMutation.isPending && setEditor(null)}
          onSave={(data) =>
            saveMutation.mutate({ kind: "edit-year", year: editor.year, data })
          }
        />
      )}
      {editor?.kind === "create-semester" && (
        <SemesterFormModal
          key={`create-semester-${editor.year.id}`}
          year={editor.year}
          pending={saveMutation.isPending}
          error={error}
          onClose={() => !saveMutation.isPending && setEditor(null)}
          onSave={(data) =>
            saveMutation.mutate({ kind: "create-semester", year: editor.year, data })
          }
        />
      )}
      {editor?.kind === "edit-semester" && (
        <SemesterFormModal
          key={`edit-semester-${editor.semester.id}`}
          year={editor.year}
          semester={editor.semester}
          pending={saveMutation.isPending}
          error={error}
          onClose={() => !saveMutation.isPending && setEditor(null)}
          onSave={(data) =>
            saveMutation.mutate({ kind: "edit-semester", semester: editor.semester, data })
          }
        />
      )}
      {confirmation && (
        <CalendarConfirmationModal
          confirmation={confirmation}
          activeYear={activeYear}
          activeSemester={activeSemester}
          pending={actionMutation.isPending}
          error={error}
          onClose={() => !actionMutation.isPending && setConfirmation(null)}
          onConfirm={() => actionMutation.mutate(confirmation)}
        />
      )}
    </div>
  );
}

function CalendarOverview({
  activeYear,
  activeSemester,
  upcomingCount,
  totalSemesters,
  canWrite,
  onCreateYear,
}: {
  activeYear?: AcademicYear;
  activeSemester?: Semester;
  upcomingCount: number;
  totalSemesters: number;
  canWrite: boolean;
  onCreateYear: () => void;
}) {
  const progress = activeYear ? getProgress(activeYear) : null;
  return (
    <section
      className="overflow-hidden rounded-3xl border border-blue-100 bg-gradient-to-l from-blue-50 via-white to-teal-50 p-5 shadow-sm sm:p-6"
      data-testid="calendar-overview"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <p className="inline-flex items-center gap-1.5 text-xs font-black text-blue-700">
            <Sparkles aria-hidden size={14} /> مركز التقويم الأكاديمي
          </p>
          <h3 className="mt-1 text-xl font-black text-slate-950">
            {activeYear ? "التشغيل الدراسي واضح ومترابط" : "ابدأ بتجهيز التقويم الدراسي"}
          </h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {activeYear
              ? "تابع العام والفصل النشطين، وجهّز المرحلة التالية دون التأثير في السجلات الحالية."
              : "أنشئ أول عام دراسي وسيتم اعتماده مباشرةً لتصبح المدرسة جاهزة للتشغيل."}
          </p>
        </div>
        {canWrite && (
          <Button onClick={onCreateYear} className="w-full sm:w-auto">
            <Plus aria-hidden size={17} /> إضافة عام دراسي
          </Button>
        )}
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <OverviewMetric
          icon={<CalendarCheck2 aria-hidden size={19} />}
          label="العام النشط"
          value={activeYear?.name ?? "غير محدد"}
          tone="blue"
        />
        <OverviewMetric
          icon={<CalendarClock aria-hidden size={19} />}
          label="الفصل النشط"
          value={activeSemester?.name ?? (activeYear ? "بانتظار التفعيل" : "غير محدد")}
          tone="teal"
        />
        <OverviewMetric
          icon={<Clock3 aria-hidden size={19} />}
          label="جاهز للمستقبل"
          value={`${formatNumber(upcomingCount)} عام · ${formatNumber(totalSemesters)} فصل`}
          tone="white"
        />
      </div>

      {activeYear && progress && (
        <div className="mt-4 rounded-2xl border border-white/80 bg-white/80 p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className="font-bold text-slate-700">
              من <time dateTime={activeYear.start_date}>{formatDate(activeYear.start_date)}</time> إلى{" "}
              <time dateTime={activeYear.end_date}>{formatDate(activeYear.end_date)}</time>
            </span>
            <span className="font-black text-blue-700">{progress.label}</span>
          </div>
          <div
            className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100"
            role="progressbar"
            aria-label="تقدم العام الدراسي"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress.percent}
          >
            <div
              className="h-full rounded-full bg-gradient-to-l from-blue-600 to-teal-500 transition-all"
              style={{ width: `${progress.percent}%` }}
            />
          </div>
        </div>
      )}
    </section>
  );
}

function OverviewMetric({
  icon,
  label,
  value,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone: "blue" | "teal" | "white";
}) {
  const tones = {
    blue: "bg-blue-600 text-white",
    teal: "bg-teal-600 text-white",
    white: "bg-white text-slate-900 ring-1 ring-slate-200",
  };
  return (
    <div className={`rounded-2xl p-4 ${tones[tone]}`}>
      <span className="flex items-center gap-2 text-xs font-bold opacity-85">
        {icon} {label}
      </span>
      <strong className="mt-2 block truncate text-base font-black" title={value}>
        {value}
      </strong>
    </div>
  );
}

function YearCard({
  year,
  activeYear,
  canWrite,
  busy,
  onEdit,
  onAddSemester,
  onEditSemester,
  onAction,
}: {
  year: AcademicYear;
  activeYear?: AcademicYear;
  canWrite: boolean;
  busy: boolean;
  onEdit: () => void;
  onAddSemester: () => void;
  onEditSemester: (semester: Semester) => void;
  onAction: (action: NonNullable<CalendarConfirmation>) => void;
}) {
  const editable = year.status === "ACTIVE" || year.status === "UPCOMING";
  const canAddSemester = editable && getAvailableSequence(year) !== null;
  const cardTone =
    year.status === "ACTIVE"
      ? "border-emerald-200 bg-white shadow-emerald-900/5"
      : year.status === "UPCOMING"
        ? "border-blue-200 bg-white shadow-blue-900/5"
        : "border-slate-200 bg-white/80 shadow-slate-900/5";
  const titleId = `academic-year-title-${year.id}`;

  return (
    <article
      role="region"
      aria-labelledby={titleId}
      data-testid="academic-year-card"
      data-year-id={year.id}
      className={`overflow-hidden rounded-3xl border shadow-sm ${cardTone}`}
    >
      <header className="border-b border-slate-100 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <span
              className={`grid size-11 shrink-0 place-items-center rounded-2xl ${
                year.status === "ACTIVE"
                  ? "bg-emerald-50 text-emerald-700"
                  : year.status === "UPCOMING"
                    ? "bg-blue-50 text-blue-700"
                    : "bg-slate-100 text-slate-500"
              }`}
            >
              <CalendarDays aria-hidden size={21} />
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h4 id={titleId} className="text-lg font-black text-slate-950">
                  {year.name}
                </h4>
                <StatusBadge status={year.status} />
              </div>
              <p className="mt-1 text-sm text-slate-500">
                من <time dateTime={year.start_date}>{formatDate(year.start_date)}</time> إلى{" "}
                <time dateTime={year.end_date}>{formatDate(year.end_date)}</time>
              </p>
              <p className="mt-1 text-xs font-bold text-slate-400">
                {formatNumber(durationDays(year.start_date, year.end_date))} يومًا ·{" "}
                {formatNumber(year.semesters.length)} فصل دراسي
              </p>
            </div>
          </div>

          {canWrite && (
            <div className="flex w-full flex-wrap gap-2 sm:w-auto sm:justify-end">
              {editable && (
                <CalendarAction
                  label={`تعديل العام «${year.name}»`}
                  icon={<Pencil aria-hidden size={15} />}
                  onClick={onEdit}
                  disabled={busy}
                >
                  تعديل
                </CalendarAction>
              )}
              {year.status === "UPCOMING" && (
                <CalendarAction
                  label={`تفعيل العام «${year.name}»`}
                  icon={<Power aria-hidden size={15} />}
                  tone="green"
                  onClick={() => onAction({ kind: "activate-year", year })}
                  disabled={busy}
                >
                  تفعيل العام
                </CalendarAction>
              )}
              {year.status === "ACTIVE" && (
                <CalendarAction
                  label={`إغلاق العام «${year.name}»`}
                  icon={<Archive aria-hidden size={15} />}
                  tone="amber"
                  onClick={() => onAction({ kind: "close-year", year })}
                  disabled={busy}
                >
                  إنهاء العام
                </CalendarAction>
              )}
              {(year.status === "UPCOMING" || year.status === "CLOSED") && (
                <CalendarAction
                  label={`أرشفة العام «${year.name}»`}
                  icon={<Archive aria-hidden size={15} />}
                  onClick={() => onAction({ kind: "archive-year", year })}
                  disabled={busy}
                >
                  أرشفة
                </CalendarAction>
              )}
            </div>
          )}
        </div>

        {year.status === "UPCOMING" && (
          <div className="mt-4 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm leading-6 text-blue-900">
            <strong>عام جاهز للمستقبل.</strong> يمكنك تعديل مواعيده وتجهيز فصوله، ثم تفعيله عند بدء العمل به.
            {activeYear && activeYear.id !== year.id && ` سيُغلق العام «${activeYear.name}» تلقائيًا عند التفعيل.`}
          </div>
        )}
        {year.status === "ACTIVE" && !year.semesters.some((item) => item.status === "ACTIVE") && (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
            <span><strong>العام نشط بلا فصل نشط.</strong> أضف الفصل الحالي أو فعّل فصلًا قادمًا.</span>
            {canWrite && canAddSemester && (
              <button type="button" className="font-black text-amber-900 underline underline-offset-4" onClick={onAddSemester}>
                إضافة الفصل الحالي
              </button>
            )}
          </div>
        )}
      </header>

      <div className="p-4 sm:p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h5 className="text-sm font-black text-slate-900">الفصول الدراسية</h5>
            <p className="mt-0.5 text-xs text-slate-500">كل تفعيل يغلق الفصل النشط السابق تلقائيًا.</p>
          </div>
          {canWrite && canAddSemester && (
            <Button
              variant="secondary"
              size="sm"
              aria-label={`إضافة فصل إلى العام ${year.name}`}
              onClick={onAddSemester}
              disabled={busy}
            >
              <Plus aria-hidden size={15} /> إضافة فصل
            </Button>
          )}
        </div>

        {year.semesters.length > 0 ? (
          <ol className="grid gap-3 lg:grid-cols-2">
            {[...year.semesters]
              .sort((a, b) => a.sequence - b.sequence)
              .map((semester) => {
                const canEditSemester = editable && semester.status !== "CLOSED";
                const canActivate = year.status === "ACTIVE" && semester.status === "UPCOMING";
                return (
                  <li
                    key={semester.id}
                    data-testid={`semester-${semester.id}`}
                    aria-label={`${semester.name} — ${year.name}`}
                    className={`rounded-2xl border p-3.5 ${
                      semester.status === "ACTIVE"
                        ? "border-emerald-200 bg-emerald-50/60"
                        : "border-slate-200 bg-slate-50/70"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <span
                        className={`grid size-9 shrink-0 place-items-center rounded-xl text-xs font-black ${
                          semester.status === "ACTIVE"
                            ? "bg-emerald-600 text-white"
                            : "bg-white text-slate-600 ring-1 ring-slate-200"
                        }`}
                      >
                        {formatNumber(semester.sequence)}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <strong className="text-sm text-slate-950">{semester.name}</strong>
                          <StatusBadge status={semester.status} />
                        </div>
                        <p className="mt-1 text-xs leading-5 text-slate-500">
                          من <time dateTime={semester.start_date}>{formatDate(semester.start_date)}</time> إلى{" "}
                          <time dateTime={semester.end_date}>{formatDate(semester.end_date)}</time>
                        </p>
                      </div>
                    </div>
                    {canWrite && (canEditSemester || canActivate) && (
                      <div className="mt-3 flex flex-wrap justify-end gap-2 border-t border-slate-200/70 pt-3">
                        {canEditSemester && (
                          <CalendarAction
                            label={`تعديل الفصل «${semester.name}» ضمن العام «${year.name}»`}
                            icon={<Pencil aria-hidden size={14} />}
                            onClick={() => onEditSemester(semester)}
                            disabled={busy}
                          >
                            تعديل
                          </CalendarAction>
                        )}
                        {canActivate && (
                          <CalendarAction
                            label={`تفعيل الفصل «${semester.name}» ضمن العام «${year.name}»`}
                            icon={<CheckCircle2 aria-hidden size={14} />}
                            tone="green"
                            onClick={() => onAction({ kind: "activate-semester", year, semester })}
                            disabled={busy}
                          >
                            تفعيل الفصل
                          </CalendarAction>
                        )}
                      </div>
                    )}
                    {year.status === "UPCOMING" && semester.status === "UPCOMING" && (
                      <p className="mt-3 border-t border-slate-200/70 pt-3 text-xs font-bold text-blue-700">
                        يصبح قابلًا للتفعيل بعد اعتماد العام.
                      </p>
                    )}
                  </li>
                );
              })}
          </ol>
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center">
            <CalendarClock aria-hidden size={25} className="mx-auto text-slate-300" />
            <p className="mt-2 text-sm font-bold text-slate-700">لم تُضف فصول لهذا العام بعد</p>
            <p className="mt-1 text-xs text-slate-500">أضف مواعيد الفصول قبل بدء التشغيل.</p>
          </div>
        )}

        {editable && !canAddSemester && (
          <p className="mt-3 rounded-xl bg-slate-100 px-3 py-2 text-xs font-bold text-slate-600">
            تم استخدام جميع ترتيبات الفصول المتاحة لهذا العام.
          </p>
        )}
        {!editable && (
          <p className="mt-3 text-xs font-bold text-slate-500">
            هذا سجل تاريخي محفوظ للعرض ولا يقبل تغييرات تشغيلية جديدة.
          </p>
        )}
      </div>
    </article>
  );
}

function StatusBadge({ status }: { status: CalendarStatus }) {
  const meta = STATUS_META[status];
  return (
    <Badge tone={meta.tone} dot data-testid="calendar-status">
      {meta.label}
    </Badge>
  );
}

function CalendarAction({
  label,
  icon,
  children,
  tone = "slate",
  ...props
}: {
  label: string;
  icon: ReactNode;
  children: ReactNode;
  tone?: "slate" | "amber" | "green";
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  const tones = {
    slate: "border-slate-200 text-slate-700 hover:bg-slate-50",
    amber: "border-amber-200 text-amber-900 hover:bg-amber-50",
    green: "border-emerald-200 text-emerald-800 hover:bg-emerald-50",
  };
  return (
    <button
      type="button"
      aria-label={label}
      className={`inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl border bg-white px-3 text-xs font-bold transition disabled:cursor-not-allowed disabled:opacity-45 ${tones[tone]}`}
      {...props}
    >
      {icon}
      {children}
    </button>
  );
}

function EmptyCalendar({ canWrite, onCreate }: { canWrite: boolean; onCreate: () => void }) {
  return (
    <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-8 text-center sm:p-10">
      <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-blue-50 text-blue-700">
        <CalendarDays aria-hidden size={27} />
      </span>
      <h4 className="mt-4 text-lg font-black text-slate-900">لا يوجد تقويم دراسي بعد</h4>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
        أنشئ العام الأول، ثم أضف الفصل الحالي ليعمل الحضور والتقارير ضمن نطاق واضح.
      </p>
      {canWrite && (
        <Button onClick={onCreate} className="mt-5">
          <Plus aria-hidden size={17} /> إنشاء أول عام
        </Button>
      )}
    </div>
  );
}

function YearFormModal({
  year,
  years,
  activeYear,
  pending,
  error,
  onClose,
  onSave,
}: {
  year?: AcademicYear;
  years: AcademicYear[];
  activeYear?: AcademicYear;
  pending: boolean;
  error: string | null;
  onClose: () => void;
  onSave: (data: YearFormValue) => void;
}) {
  const suggested = getYearDefaults(years);
  const [name, setName] = useState(year?.name ?? suggested.name);
  const [start, setStart] = useState(year?.start_date ?? suggested.start_date);
  const [end, setEnd] = useState(year?.end_date ?? suggested.end_date);
  const [nameIsAutomatic, setNameIsAutomatic] = useState(!year);
  const [formError, setFormError] = useState<string | null>(null);
  const activate = !year && !activeYear;

  const updateDates = (nextStart: string, nextEnd: string) => {
    setStart(nextStart);
    setEnd(nextEnd);
    if (nameIsAutomatic) {
      const nextName = academicYearName(nextStart, nextEnd);
      if (nextName) setName(nextName);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setFormError(null);
    if (!name.trim() || !start || !end) {
      setFormError("أكمل اسم العام وتاريخي البداية والنهاية.");
      return;
    }
    if (start >= end) {
      setFormError("تاريخ بداية العام يجب أن يسبق تاريخ نهايته.");
      return;
    }
    const outsideSemester = year?.semesters.find(
      (semester) => semester.start_date < start || semester.end_date > end,
    );
    if (outsideSemester) {
      setFormError(`لا يمكن تقليص العام لأن الفصل «${outsideSemester.name}» سيصبح خارج حدوده.`);
      return;
    }
    onSave({ name: name.trim(), start_date: start, end_date: end, activate });
  };

  return (
    <Modal
      title={year ? `تعديل العام «${year.name}»` : "إضافة عام دراسي"}
      description={
        year
          ? "حدّث الاسم أو المواعيد مع بقاء الفصول والسجلات مرتبطة بالعام نفسه."
          : "جهّز حدود العام الآن، ثم أضف فصوله من بطاقة العام."
      }
      onClose={onClose}
    >
      <form aria-label={year ? `تعديل العام «${year.name}»` : "إنشاء عام دراسي"} onSubmit={submit}>
        <div
          className={`mb-5 rounded-2xl border p-4 text-sm leading-6 ${
            year
              ? "border-slate-200 bg-slate-50 text-slate-700"
              : activate
                ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                : "border-blue-200 bg-blue-50 text-blue-900"
          }`}
        >
          <p className="font-black">
            {year
              ? "التعديل لا ينشئ عامًا جديدًا."
              : activate
                ? "هذا أول عام وسيُفعّل مباشرةً."
                : "سيُحفظ كعام قادم بأمان."}
          </p>
          <p className="mt-1">
            {year
              ? "لن يقبل النظام نطاقًا يترك أحد الفصول المسجلة خارج بداية العام أو نهايته."
              : activate
                ? "يتم الإنشاء والتفعيل ذريًا في خطوة واحدة، ثم يمكنك إضافة الفصل الحالي."
                : `لن يتأثر العام النشط «${activeYear?.name}» حتى تختار تفعيل العام الجديد لاحقًا.`}
          </p>
        </div>

        <TextField
          label="اسم العام"
          description="مثال: 2027/2028"
          required
          data-dialog-initial-focus
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            setNameIsAutomatic(false);
          }}
        />
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <TextField
            label="بداية العام"
            type="date"
            dir="ltr"
            required
            value={start}
            onChange={(event) => updateDates(event.target.value, end)}
          />
          <TextField
            label="نهاية العام"
            type="date"
            dir="ltr"
            required
            value={end}
            onChange={(event) => updateDates(start, event.target.value)}
          />
        </div>
        {start && end && start < end && (
          <p className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-xs font-bold text-slate-600">
            مدة العام: {formatNumber(durationDays(start, end))} يومًا · من {formatDate(start)} إلى {formatDate(end)}
          </p>
        )}
        {(formError || error) && (
          <p role="alert" className="mt-4 rounded-xl bg-red-50 px-3 py-2 text-sm font-bold text-red-700">
            {formError ?? error}
          </p>
        )}
        <div className="mt-6 flex flex-col-reverse gap-2 border-t border-slate-100 pt-4 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={onClose} disabled={pending} className="w-full sm:w-auto">
            إلغاء
          </Button>
          <Button
            type="submit"
            loading={pending}
            loadingLabel="جارٍ الحفظ..."
            className="w-full sm:w-auto"
          >
            {year ? <Pencil aria-hidden size={16} /> : <Plus aria-hidden size={16} />}
            {year ? "حفظ تعديلات العام" : activate ? "إنشاء العام وتفعيله" : "حفظ كعام قادم"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function SemesterFormModal({
  year,
  semester,
  pending,
  error,
  onClose,
  onSave,
}: {
  year: AcademicYear;
  semester?: Semester;
  pending: boolean;
  error: string | null;
  onClose: () => void;
  onSave: (data: SemesterFormValue) => void;
}) {
  const suggested = getSemesterDefaults(year);
  const [name, setName] = useState(semester?.name ?? suggested.name);
  const [sequence, setSequence] = useState(semester?.sequence ?? suggested.sequence);
  const [start, setStart] = useState(semester?.start_date ?? suggested.start_date);
  const [end, setEnd] = useState(semester?.end_date ?? suggested.end_date);
  const [formError, setFormError] = useState<string | null>(null);
  const activate =
    !semester &&
    year.status === "ACTIVE" &&
    !year.semesters.some((item) => item.status === "ACTIVE");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setFormError(null);
    if (!name.trim() || !start || !end) {
      setFormError("أكمل اسم الفصل وترتيبه وتاريخي البداية والنهاية.");
      return;
    }
    if (sequence < 1 || sequence > 10) {
      setFormError("ترتيب الفصل يجب أن يكون بين 1 و10.");
      return;
    }
    if (start > end) {
      setFormError("تاريخ بداية الفصل يجب ألا يتجاوز تاريخ نهايته.");
      return;
    }
    if (start < year.start_date || end > year.end_date) {
      setFormError(`يجب أن تكون مواعيد الفصل ضمن حدود العام ${year.name}.`);
      return;
    }
    const duplicateSequence = year.semesters.find(
      (item) => item.id !== semester?.id && item.sequence === sequence,
    );
    if (duplicateSequence) {
      setFormError(`الترتيب ${formatNumber(sequence)} مستخدم بالفعل للفصل «${duplicateSequence.name}».`);
      return;
    }
    const overlap = year.semesters.find(
      (item) =>
        item.id !== semester?.id && start <= item.end_date && end >= item.start_date,
    );
    if (overlap) {
      setFormError(`تتداخل هذه المواعيد مع الفصل «${overlap.name}».`);
      return;
    }
    onSave({ name: name.trim(), sequence, start_date: start, end_date: end, activate });
  };

  return (
    <Modal
      title={semester ? `تعديل الفصل «${semester.name}»` : `إضافة فصل إلى ${year.name}`}
      description={
        semester
          ? "صحّح الاسم أو الترتيب أو المواعيد مع الحفاظ على سجل الفصل."
          : "حدّد الفصل داخل حدود العام دون أي تداخل مع الفصول الأخرى."
      }
      onClose={onClose}
    >
      <form
        aria-label={semester ? `تعديل الفصل «${semester.name}»` : `إضافة فصل إلى العام ${year.name}`}
        onSubmit={submit}
      >
        <div className="mb-5 rounded-2xl border border-blue-100 bg-blue-50 p-4 text-sm leading-6 text-blue-900">
          <p className="font-black">حدود العام: من {formatDate(year.start_date)} إلى {formatDate(year.end_date)}</p>
          <p className="mt-1">
            {semester
              ? "تغيير البيانات لا يغيّر حالة الفصل الحالية."
              : activate
                ? "لا يوجد فصل نشط؛ سيُنشأ هذا الفصل ويُفعّل ذريًا في خطوة واحدة."
                : year.status === "UPCOMING"
                  ? "سيُحفظ الفصل كقادم، ويمكن تفعيله بعد اعتماد العام."
                  : "سيُحفظ الفصل كقادم دون التأثير في الفصل النشط."}
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_8rem]">
          <TextField
            label="اسم الفصل"
            required
            data-dialog-initial-focus
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <TextField
            label="الترتيب"
            type="number"
            min={1}
            max={10}
            required
            value={sequence}
            onChange={(event) => setSequence(Number(event.target.value))}
          />
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <TextField
            label="بداية الفصل"
            type="date"
            dir="ltr"
            min={year.start_date}
            max={year.end_date}
            required
            value={start}
            onChange={(event) => setStart(event.target.value)}
          />
          <TextField
            label="نهاية الفصل"
            type="date"
            dir="ltr"
            min={year.start_date}
            max={year.end_date}
            required
            value={end}
            onChange={(event) => setEnd(event.target.value)}
          />
        </div>
        {start && end && start <= end && (
          <p className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-xs font-bold text-slate-600">
            مدة الفصل: {formatNumber(durationDays(start, end))} يومًا
          </p>
        )}
        {(formError || error) && (
          <p role="alert" className="mt-4 rounded-xl bg-red-50 px-3 py-2 text-sm font-bold text-red-700">
            {formError ?? error}
          </p>
        )}
        <div className="mt-6 flex flex-col-reverse gap-2 border-t border-slate-100 pt-4 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={onClose} disabled={pending} className="w-full sm:w-auto">
            إلغاء
          </Button>
          <Button
            type="submit"
            loading={pending}
            loadingLabel="جارٍ الحفظ..."
            className="w-full sm:w-auto"
          >
            {semester ? <Pencil aria-hidden size={16} /> : <Plus aria-hidden size={16} />}
            {semester ? "حفظ تعديلات الفصل" : activate ? "إنشاء الفصل وتفعيله" : "حفظ الفصل"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function CalendarConfirmationModal({
  confirmation,
  activeYear,
  activeSemester,
  pending,
  error,
  onClose,
  onConfirm,
}: {
  confirmation: NonNullable<CalendarConfirmation>;
  activeYear?: AcademicYear;
  activeSemester?: Semester;
  pending: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: () => void;
}) {
  let title: string;
  let description: string;
  let headline: string;
  let detail: string;
  let confirmLabel: string;
  let danger = false;

  if (confirmation.kind === "activate-year") {
    title = `تفعيل العام «${confirmation.year.name}»`;
    description = "سيصبح هذا العام هو السياق التشغيلي الوحيد للمدرسة.";
    headline = activeYear
      ? `سيُغلق العام النشط «${activeYear.name}» تلقائيًا.`
      : "سيصبح هذا أول عام نشط للمدرسة.";
    detail = activeSemester
      ? `وسيُغلق الفصل النشط «${activeSemester.name}» للحفاظ على اتساق التقويم.`
      : "بعد التفعيل اختر الفصل الجاري أو أضفه إن لم يكن موجودًا.";
    confirmLabel = "تأكيد تفعيل العام";
  } else if (confirmation.kind === "close-year") {
    title = `إنهاء العام «${confirmation.year.name}»`;
    description = "ينهي هذا الإجراء السياق التشغيلي الحالي ويحفظ جميع السجلات.";
    headline = "ستتوقف العمليات التي تتطلب عامًا نشطًا حتى تفعّل عامًا آخر.";
    detail = activeSemester
      ? `سيُغلق أيضًا الفصل النشط «${activeSemester.name}» في العملية نفسها.`
      : "لن تُحذف بيانات أو تقارير أو سجلات حضور.";
    confirmLabel = "تأكيد إنهاء العام";
    danger = true;
  } else if (confirmation.kind === "archive-year") {
    title = `أرشفة العام «${confirmation.year.name}»`;
    description = "تنقل الأرشفة العام إلى السجل التاريخي وتحميه من التفعيل العرضي.";
    headline = "سيبقى العام وفصوله متاحين للعرض والتقارير التاريخية.";
    detail = "لا يمكن تفعيل عام مؤرشف، ولا يتم حذف أي سجل عند الأرشفة.";
    confirmLabel = "تأكيد الأرشفة";
  } else {
    title = `تفعيل الفصل «${confirmation.semester.name}»`;
    description = `سيصبح الفصل النشط للعام ${confirmation.year.name}.`;
    headline = activeSemester
      ? `سيُغلق الفصل النشط «${activeSemester.name}» تلقائيًا.`
      : "سيصبح هذا أول فصل نشط في العام.";
    detail = "تظل سجلات الفصل السابق محفوظة، ويبدأ التشغيل الجديد ضمن هذا الفصل.";
    confirmLabel = "تأكيد تفعيل الفصل";
  }

  return (
    <Modal title={title} description={description} onClose={onClose}>
      <div
        className={`rounded-2xl border p-4 text-sm leading-6 ${
          danger
            ? "border-amber-200 bg-amber-50 text-amber-950"
            : "border-blue-200 bg-blue-50 text-blue-950"
        }`}
      >
        <p className="font-black">{headline}</p>
        <p className="mt-1">{detail}</p>
      </div>
      {error && (
        <p role="alert" className="mt-4 rounded-xl bg-red-50 px-3 py-2 text-sm font-bold text-red-700">
          {error}
        </p>
      )}
      <div className="mt-6 flex flex-col-reverse gap-2 border-t border-slate-100 pt-4 sm:flex-row sm:justify-end">
        <Button variant="secondary" onClick={onClose} disabled={pending} className="w-full sm:w-auto">
          تراجع
        </Button>
        <Button
          variant={danger ? "danger" : "primary"}
          onClick={onConfirm}
          loading={pending}
          loadingLabel="جارٍ التنفيذ..."
          className="w-full sm:w-auto"
        >
          {danger ? <Archive aria-hidden size={16} /> : <Power aria-hidden size={16} />}
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}

function apiMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function parseIsoDate(value: string): Date {
  const [year, month, day] = value.split("-");
  return new Date(Number(year), Number(month) - 1, Number(day), 12);
}

function isoDate(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function formatDate(value: string): string {
  return arabicDateFormatter.format(parseIsoDate(value));
}

function formatNumber(value: number): string {
  return arabicNumberFormatter.format(value);
}

function durationDays(start: string, end: string): number {
  return Math.max(
    1,
    Math.round((parseIsoDate(end).getTime() - parseIsoDate(start).getTime()) / DAY_IN_MS) + 1,
  );
}

function addDays(value: string, days: number): string {
  const date = parseIsoDate(value);
  date.setDate(date.getDate() + days);
  return isoDate(date.getFullYear(), date.getMonth() + 1, date.getDate());
}

function shiftOneYear(value: string): string {
  const [yearText, monthText, dayText] = value.split("-");
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const lastDay = new Date(year + 1, month, 0).getDate();
  return isoDate(year + 1, month, Math.min(day, lastDay));
}

function academicYearName(start: string, end: string): string {
  if (!start || !end) return "";
  return `${start.slice(0, 4)}/${end.slice(0, 4)}`;
}

function getYearDefaults(years: AcademicYear[]): Omit<YearFormValue, "activate"> {
  const latest = [...years].sort((a, b) => b.end_date.localeCompare(a.end_date))[0];
  if (latest) {
    const start = shiftOneYear(latest.start_date);
    const end = shiftOneYear(latest.end_date);
    return { name: academicYearName(start, end), start_date: start, end_date: end };
  }
  const currentYear = new Date().getFullYear();
  return { name: `${currentYear}/${currentYear + 1}`, start_date: "", end_date: "" };
}

function getAvailableSequence(year: AcademicYear): number | null {
  const used = new Set(year.semesters.map((semester) => semester.sequence));
  for (let sequence = 1; sequence <= 10; sequence += 1) {
    if (!used.has(sequence)) return sequence;
  }
  return null;
}

function getSemesterDefaults(year: AcademicYear): Omit<SemesterFormValue, "activate"> {
  const sequence = getAvailableSequence(year) ?? 10;
  const latest = [...year.semesters].sort((a, b) => b.end_date.localeCompare(a.end_date))[0];
  const suggestedStart = latest ? addDays(latest.end_date, 1) : year.start_date;
  return {
    name: `الفصل الدراسي ${sequence}`,
    sequence,
    start_date: suggestedStart <= year.end_date ? suggestedStart : "",
    end_date: latest && suggestedStart <= year.end_date ? year.end_date : "",
  };
}

function getProgress(year: AcademicYear): { percent: number; label: string } {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12);
  const start = parseIsoDate(year.start_date);
  const end = parseIsoDate(year.end_date);
  if (today < start) {
    const days = Math.ceil((start.getTime() - today.getTime()) / DAY_IN_MS);
    return { percent: 0, label: `يبدأ بعد ${formatNumber(days)} يومًا` };
  }
  if (today > end) return { percent: 100, label: "اكتملت مدة العام" };
  const total = Math.max(1, end.getTime() - start.getTime());
  const elapsed = Math.max(0, today.getTime() - start.getTime());
  const percent = Math.min(100, Math.max(0, Math.round((elapsed / total) * 100)));
  const remaining = Math.ceil((end.getTime() - today.getTime()) / DAY_IN_MS);
  return { percent, label: `متبقي ${formatNumber(remaining)} يومًا` };
}

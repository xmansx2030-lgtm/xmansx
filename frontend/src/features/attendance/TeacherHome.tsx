import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BookOpenCheck, Clock3, GraduationCap, ScanLine, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { getAttendanceSections, getCurrentPeriod } from "@/features/attendance/api";
import { QrScanner } from "@/features/attendance/QrScanner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";

interface TeacherHomeProps {
  activeSchoolId: number;
}

/** شاشة المعلم: الحصة الحالية + فصول المدرسة + مسح QR — Mobile-first. */
export function TeacherHome({ activeSchoolId }: TeacherHomeProps) {
  const navigate = useNavigate();
  const me = useMe();
  const [scanning, setScanning] = useState(false);
  const [sectionSearch, setSectionSearch] = useState("");

  const periodQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "current-period"),
    queryFn: ({ signal }) => getCurrentPeriod(signal),
    refetchInterval: 60_000, // الحصة تتغير مع الوقت
  });

  const sectionsQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "sections"),
    queryFn: ({ signal }) => getAttendanceSections(signal),
  });

  const period = periodQuery.data?.period;
  const filteredSections = useMemo(() => {
    const query = sectionSearch.trim().toLocaleLowerCase("ar");
    return [...(sectionsQuery.data ?? [])]
      .sort((a, b) =>
        `${a.grade_name} ${a.name}`.localeCompare(`${b.grade_name} ${b.name}`, "ar", {
          numeric: true,
        }),
      )
      .filter((section) =>
        `${section.grade_name} ${section.name}`.toLocaleLowerCase("ar").includes(query),
      );
  }, [sectionSearch, sectionsQuery.data]);

  return (
    <div className="space-y-5">
      <PageHeader
        icon={BookOpenCheck}
        eyebrow="مساحة المعلم اليومية"
        title={`مرحبًا ${me.data?.name ?? "بك"}`}
        description="ابدأ التحضير بسرعة عبر مسح رمز الفصل، أو اختر الفصل يدويًا عند الحاجة."
        tone="teacher"
        badge={me.data?.active_school?.name ?? "المعلم"}
        meta={period ? <><Clock3 aria-hidden size={14} /> {period.name} · <span dir="ltr">{period.start_time} – {period.end_time}</span></> : "تظهر الحصة الحالية تلقائيًا حسب جدول المدرسة"}
        actions={
          <Button
            variant="secondary"
            onClick={() => setScanning((value) => !value)}
            className="border-white/15 !bg-white !text-slate-950 shadow-lg hover:!bg-slate-50"
          >
            <ScanLine aria-hidden size={18} /> {scanning ? "إغلاق الماسح" : "مسح رمز الفصل"}
          </Button>
        }
        testId="teacher-workspace-header"
      />

      <section
        className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5"
        data-testid="current-period-card"
      >
        {periodQuery.isPending && <Spinner label="جارٍ تحديد الحصة الحالية..." />}
        {periodQuery.isError && <ErrorState error={periodQuery.error} />}
        {periodQuery.isSuccess && period && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="grid size-11 place-items-center rounded-2xl bg-emerald-50 text-emerald-700"><Clock3 aria-hidden size={21} /></span>
              <div>
              <p className="text-xs font-bold text-slate-500">الحصة الحالية</p>
              <p className="mt-0.5 text-lg font-black text-slate-900" data-testid="current-period-name">
                {period.name}
              </p>
              </div>
            </div>
            <p className="rounded-xl bg-slate-100 px-3 py-2 text-sm font-bold text-slate-700" dir="ltr">
              {period.start_time} – {period.end_time}
            </p>
          </div>
        )}
        {periodQuery.isSuccess && !period && (
          <div className="flex items-center gap-3 text-slate-600" data-testid="no-current-period"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-500"><Clock3 aria-hidden size={19} /></span><div><p className="font-bold text-slate-800">لا توجد حصة حالية</p><p className="mt-0.5 text-sm">التحضير متاح أثناء الحصص حسب جدول المدرسة.</p></div></div>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="mb-4 flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-teal-50 text-teal-700"><GraduationCap aria-hidden size={20} /></span>
          <div><h2 className="text-lg font-black text-slate-900">اختيار الفصل</h2><p className="mt-1 text-xs text-slate-500">الفصول المتاحة لك في المدرسة الحالية.</p></div>
        </div>

        {scanning && (
          <div className="mb-4">
            <QrScanner
              onToken={(token) => navigate(`/qr/${encodeURIComponent(token)}`)}
              onClose={() => setScanning(false)}
            />
          </div>
        )}

        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-slate-700">أو اختر الفصل يدويًا</p>
            {sectionsQuery.isSuccess && (
              <p className="mt-1 text-xs text-slate-500" aria-live="polite">
                {sectionSearch.trim()
                  ? `${filteredSections.length} من ${sectionsQuery.data.length} فصل`
                  : `${sectionsQuery.data.length} فصل متاح`}
              </p>
            )}
          </div>
          {sectionsQuery.isSuccess && sectionsQuery.data.length > 6 && (
            <label className="relative block w-full sm:w-72">
              <span className="sr-only">بحث عن فصل</span>
              <Search
                aria-hidden
                size={17}
                className="pointer-events-none absolute end-3 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <input
                type="search"
                value={sectionSearch}
                onChange={(event) => setSectionSearch(event.target.value)}
                placeholder="ابحث باسم الصف أو الفصل"
                className="w-full pe-10 ps-3"
                data-testid="section-search"
              />
            </label>
          )}
        </div>
        {sectionsQuery.isPending && <Spinner label="جارٍ تحميل الفصول..." />}
        {sectionsQuery.isError && <ErrorState error={sectionsQuery.error} />}
        {sectionsQuery.isSuccess && sectionsQuery.data.length === 0 && (
          <EmptyState title="لا توجد فصول نشطة" description="عند إضافة الفصول وربطها بالعام الدراسي ستظهر هنا تلقائيًا." testId="no-sections" />
        )}
        {sectionsQuery.isSuccess && sectionsQuery.data.length > 0 && filteredSections.length === 0 && (
          <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center">
            <p className="font-medium text-slate-700">لا يوجد فصل مطابق</p>
            <p className="mt-1 text-sm text-slate-500">جرّب اسم الصف أو رقم الفصل.</p>
            <button
              type="button"
              className="mt-3 text-sm font-semibold text-blue-700 underline"
              onClick={() => setSectionSearch("")}
            >
              مسح البحث
            </button>
          </div>
        )}
        {sectionsQuery.isSuccess && filteredSections.length > 0 && (
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3" data-testid="sections-list">
            {filteredSections.map((section) => (
              <li key={section.id}>
                <button
                  type="button"
                  className="group flex w-full items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-gradient-to-b from-white to-slate-50 p-4 text-start shadow-sm transition-all hover:-translate-y-0.5 hover:border-teal-300 hover:shadow-md"
                  onClick={() => navigate(`/attendance/section/${section.id}`)}
                  data-testid={`section-${section.id}`}
                >
                  <span><span className="block font-black text-slate-900">{section.name}</span><span className="mt-1 block text-xs text-slate-500">{section.grade_name} · {section.students_count} طالبًا</span></span>
                  <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-500 transition group-hover:bg-teal-600 group-hover:text-white"><ArrowLeft aria-hidden size={17} /></span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  BellRing,
  BookOpenCheck,
  Clock3,
  GraduationCap,
  MessageSquareReply,
  ScanLine,
  Search,
  Send,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { adaptivePollingInterval, POLLING } from "@/app/polling";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { getAttendanceSections, getCurrentPeriod } from "@/features/attendance/api";
import { QrScanner } from "@/features/attendance/QrScanner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { getMyFollowUpRequests } from "@/features/counseling/api";
import { getMyReferrals } from "@/features/referrals/api";
import { roleLabel, studentCountLabel } from "@/utils/roles";

interface TeacherHomeProps {
  activeSchoolId: number;
}

const teacherPeriodPollInterval = adaptivePollingInterval(POLLING.teacherPeriod);
const teacherAttentionPollInterval = adaptivePollingInterval(POLLING.teacherAttention);
const INITIAL_VISIBLE_SECTIONS = 12;
const SECTION_PAGE_SIZE = 12;

/** شاشة المعلم: الحصة الحالية + جميع الفصول النشطة + مسح QR — Mobile-first. */
export function TeacherHome({ activeSchoolId }: TeacherHomeProps) {
  const navigate = useNavigate();
  const me = useMe();
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const [scanning, setScanning] = useState(false);
  const [sectionSearch, setSectionSearch] = useState("");
  const [visibleSectionCount, setVisibleSectionCount] = useState(INITIAL_VISIBLE_SECTIONS);

  const periodQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "current-period"),
    queryFn: ({ signal }) => getCurrentPeriod(signal),
    refetchInterval: teacherPeriodPollInterval,
    // التبويب المخفي لا يحتاج تحديثًا حيًا؛ TanStack يعيد الجلب عند العودة.
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: "always",
  });

  const sectionsQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "sections"),
    queryFn: ({ signal }) => getAttendanceSections(signal),
  });

  const followUpsQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "my-follow-up-requests"),
    queryFn: ({ signal }) => getMyFollowUpRequests(signal),
    refetchInterval: teacherAttentionPollInterval,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: "always",
  });

  const referralsQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "my-referrals", "summary", "OPEN"),
    queryFn: ({ signal }) => getMyReferrals({ status: "OPEN", page: 1 }, signal),
    refetchInterval: teacherAttentionPollInterval,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: "always",
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
  const visibleSections = filteredSections.slice(0, visibleSectionCount);
  const hiddenSectionsCount = Math.max(0, filteredSections.length - visibleSections.length);
  const pendingFollowUps = (followUpsQuery.data ?? []).filter(
    (row) => row.status === "PENDING" && !row.response,
  ).length;
  const openReferrals = referralsQuery.data?.count ?? 0;
  const attentionCount = pendingFollowUps + openReferrals;

  return (
    <div className="ds-page">
      <PageHeader
        icon={BookOpenCheck}
        eyebrow={`مساحة ${roleLabel("TEACHER", schoolType)} اليومية`}
        title={`مرحبًا ${me.data?.name ?? "بك"}`}
        description="ابدأ التحضير بسرعة عبر مسح رمز الفصل، أو اختر الفصل يدويًا عند الحاجة."
        tone="teacher"
        badge={me.data?.active_school?.name ?? roleLabel("TEACHER", schoolType)}
        meta={period ? <><Clock3 aria-hidden size={14} /> {period.name} · <span dir="ltr">{period.start_time} – {period.end_time}</span></> : "تظهر الحصة الحالية تلقائيًا حسب جدول المدرسة"}
        actions={
          <Button
            variant="secondary"
            onClick={() => setScanning((value) => !value)}
            className="w-full justify-center border-white/15 !bg-white !text-slate-950 shadow-lg hover:!bg-slate-50 sm:w-auto"
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
          <div className="flex flex-col items-stretch justify-between gap-3 sm:flex-row sm:items-center">
            <div className="flex min-w-0 items-center gap-3">
              <span className="grid size-11 place-items-center rounded-2xl bg-emerald-50 text-emerald-700"><Clock3 aria-hidden size={21} /></span>
              <div className="min-w-0">
              <p className="text-xs font-bold text-slate-500">الحصة الحالية</p>
              <p className="mt-0.5 text-lg font-black text-slate-900" data-testid="current-period-name">
                {period.name}
              </p>
              </div>
            </div>
            <p className="rounded-xl bg-slate-100 px-3 py-2 text-center text-sm font-bold text-slate-700 sm:text-start" dir="ltr">
              {period.start_time} – {period.end_time}
            </p>
          </div>
        )}
        {periodQuery.isSuccess && !period && (
          <div className="flex items-center gap-3 text-slate-600" data-testid="no-current-period"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-500"><Clock3 aria-hidden size={19} /></span><div><p className="font-bold text-slate-800">لا توجد حصة حالية</p><p className="mt-0.5 text-sm">التحضير متاح أثناء الحصص حسب جدول المدرسة.</p></div></div>
        )}
      </section>

      <section
        className="overflow-hidden rounded-2xl border border-teal-100 bg-white shadow-sm"
        data-testid="teacher-attention-summary"
        aria-labelledby="teacher-attention-title"
      >
        <div className="flex flex-col gap-3 border-b border-teal-100 bg-gradient-to-l from-teal-50 to-white p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
          <div className="flex items-center gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-teal-600 text-white shadow-sm">
              <BellRing aria-hidden size={21} />
            </span>
            <div>
              <p className="text-xs font-bold text-teal-700">تنبيهات وإجراءات</p>
              <h2 id="teacher-attention-title" className="text-lg font-black text-slate-900">متابعة اليوم</h2>
              <p className="mt-0.5 text-xs leading-5 text-slate-500">ابدأ بما ينتظر ردك، ثم راجع التحويلات التي ما زالت قيد المتابعة.</p>
            </div>
          </div>
          <span
            className={`inline-flex min-h-9 items-center self-start rounded-full px-3 text-sm font-black sm:self-auto ${attentionCount > 0 ? "bg-amber-100 text-amber-900" : "bg-emerald-100 text-emerald-800"}`}
            data-testid="teacher-attention-total"
          >
            {followUpsQuery.isPending || referralsQuery.isPending
              ? "جارٍ التحديث"
              : attentionCount > 0
                ? `${attentionCount} بندًا للمتابعة`
                : "لا توجد بنود عاجلة"}
          </span>
        </div>
        <div className="grid gap-3 p-4 sm:grid-cols-2 sm:p-5">
          <Link
            to="/teacher/follow-ups"
            className="group flex min-h-24 items-center justify-between gap-4 rounded-2xl border border-amber-100 bg-amber-50/70 p-4 transition hover:-translate-y-0.5 hover:border-amber-200 hover:shadow-sm"
            data-testid="teacher-follow-ups-alert"
          >
            <span className="flex min-w-0 items-center gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white text-amber-700 shadow-sm"><MessageSquareReply aria-hidden size={19} /></span>
              <span className="min-w-0"><strong className="block text-sm text-slate-900">طلبات تحتاج ردك</strong><span className="mt-1 block text-xs leading-5 text-slate-600">ملاحظات مهنية طلبها المرشد الطلابي.</span></span>
            </span>
            <span className="text-2xl font-black text-amber-800">{followUpsQuery.isPending ? "—" : pendingFollowUps}</span>
          </Link>
          <Link
            to="/referrals/mine"
            className="group flex min-h-24 items-center justify-between gap-4 rounded-2xl border border-blue-100 bg-blue-50/70 p-4 transition hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-sm"
            data-testid="teacher-referrals-alert"
          >
            <span className="flex min-w-0 items-center gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white text-blue-700 shadow-sm"><Send aria-hidden size={19} /></span>
              <span className="min-w-0"><strong className="block text-sm text-slate-900">تحويلات قيد المتابعة</strong><span className="mt-1 block text-xs leading-5 text-slate-600">تابع الاستلام والمعالجة والإغلاق.</span></span>
            </span>
            <span className="text-2xl font-black text-blue-800">{referralsQuery.isPending ? "—" : openReferrals}</span>
          </Link>
        </div>
        {(followUpsQuery.isError || referralsQuery.isError) && (
          <p className="border-t border-amber-100 bg-amber-50 px-4 py-2 text-xs font-medium text-amber-800" role="status">تعذر تحديث بعض مؤشرات المتابعة الآن؛ يمكنك فتح الصفحة المطلوبة مباشرة.</p>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="mb-4 flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-teal-50 text-teal-700"><GraduationCap aria-hidden size={20} /></span>
          <div><h2 className="text-lg font-black text-slate-900">اختيار الفصل</h2><p className="mt-1 text-xs text-slate-500">جميع الفصول النشطة في المدرسة الحالية.</p></div>
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
                onChange={(event) => {
                  setSectionSearch(event.target.value);
                  setVisibleSectionCount(INITIAL_VISIBLE_SECTIONS);
                }}
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
            {visibleSections.map((section) => (
              <li key={section.id}>
                <button
                  type="button"
                  className="group flex w-full items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-gradient-to-b from-white to-slate-50 p-4 text-start shadow-sm transition-all hover:-translate-y-0.5 hover:border-teal-300 hover:shadow-md"
                  onClick={() => navigate(`/attendance/section/${section.id}`, {
                    state: { attendanceSource: "SECTION_LIST" },
                  })}
                  data-testid={`section-${section.id}`}
                >
                  <span className="min-w-0"><span className="block break-words font-black text-slate-900">{section.name}</span><span className="mt-1 block break-words text-xs text-slate-500">{section.grade_name} · {section.students_count} {studentCountLabel(schoolType)}</span></span>
                  <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-500 transition group-hover:bg-teal-600 group-hover:text-white"><ArrowLeft aria-hidden size={17} /></span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {sectionsQuery.isSuccess && hiddenSectionsCount > 0 && (
          <div className="mt-4 flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-3 text-center">
            <p className="text-xs font-medium text-slate-500">يُعرض {visibleSections.length} من {filteredSections.length} فصلًا لتبقى الصفحة سريعة وواضحة.</p>
            <Button
              variant="secondary"
              onClick={() => setVisibleSectionCount((count) => count + SECTION_PAGE_SIZE)}
              data-testid="show-more-sections"
            >
              عرض المزيد ({hiddenSectionsCount} متبقي)
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CheckCircle2,
  Clock3,
  FilterX,
  GraduationCap,
  Search,
  Send,
  UserRoundPlus,
} from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/Pagination";
import { Spinner } from "@/components/Spinner";
import { getAttendanceSections } from "@/features/attendance/api";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import {
  getMyReferrals,
  getReferralCandidates,
  type ReferralCandidate,
} from "@/features/referrals/api";
import { ReferralCreateCard } from "@/features/referrals/ReferralCreateCard";
import { ReferralDetailCard } from "@/features/referrals/ReferralDetailCard";
import { ReferralsTable } from "@/features/referrals/ReferralsPage";
import { useActiveSchoolId } from "@/features/settings/hooks";
import { roleLabel, studentLabel, studentPluralLabel } from "@/utils/roles";

/** مساحة المعلم لإنشاء إحالة تمر بالوكيل المسؤول قبل المرشد. */
export function MyReferralsPage() {
  const schoolId = useActiveSchoolId();
  const me = useMe();
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const queryClient = useQueryClient();
  const [selectedReferral, setSelectedReferral] = useState<number | null>(null);
  const [selectedStudent, setSelectedStudent] = useState<ReferralCandidate | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [grade, setGrade] = useState("");
  const [section, setSection] = useState("");
  const [candidatePage, setCandidatePage] = useState(1);
  const [referralPage, setReferralPage] = useState(1);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim());
    }, 300);

    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const sections = useQuery({
    queryKey: schoolScopedKey(schoolId, "attendance", "sections"),
    queryFn: ({ signal }) => getAttendanceSections(signal),
    enabled: schoolId > 0,
  });
  const candidates = useQuery({
    queryKey: schoolScopedKey(
      schoolId,
      "referral-candidates",
      search,
      grade,
      section,
      candidatePage,
    ),
    queryFn: ({ signal }) =>
      getReferralCandidates(
        {
          search: search || undefined,
          grade: grade ? Number(grade) : undefined,
          section: section ? Number(section) : undefined,
          page: candidatePage,
        },
        signal,
      ),
    enabled: schoolId > 0,
  });
  const list = useQuery({
    queryKey: schoolScopedKey(schoolId, "my-referrals", referralPage),
    queryFn: ({ signal }) => getMyReferrals({ page: referralPage }, signal),
    enabled: schoolId > 0,
  });
  const openReferrals = useQuery({
    queryKey: schoolScopedKey(schoolId, "my-referrals", "summary", "OPEN"),
    queryFn: ({ signal }) => getMyReferrals({ status: "OPEN", page: 1 }, signal),
    enabled: schoolId > 0,
  });

  const grades = useMemo(() => {
    const found = new Map<number, string>();
    for (const item of sections.data ?? []) {
      if (item.grade_id != null) found.set(item.grade_id, item.grade_name);
    }
    return [...found].map(([id, name]) => ({ id, name }));
  }, [sections.data]);
  const filteredSections = (sections.data ?? []).filter(
    (item) => grade === "" || item.grade_id === Number(grade),
  );

  const applySearch = (event: FormEvent) => {
    event.preventDefault();
    setCandidatePage(1);
    setSelectedStudent(null);
    setSearch(searchInput.trim());
  };
  const resetSearch = () => {
    setSearchInput("");
    setSearch("");
    setGrade("");
    setSection("");
    setCandidatePage(1);
    setSelectedStudent(null);
  };
  const finishReferral = (message: string, referralId: number) => {
    setNotice(message);
    setSelectedStudent(null);
    setReferralPage(1);
    setSelectedReferral(referralId);
    void queryClient.invalidateQueries({
      queryKey: schoolScopedKey(schoolId, "my-referrals"),
    });
  };

  const rows = list.data?.results ?? [];
  const total = list.data?.count ?? 0;
  const activeCount = openReferrals.data?.count ?? 0;
  const closedCount = Math.max(0, total - activeCount);
  const summaryPending = openReferrals.isPending;
  const studentSingular = studentLabel(schoolType);
  const studentPlural = studentPluralLabel(schoolType);
  const counselorLabel = roleLabel("COUNSELOR", schoolType);

  return (
    <div className="ds-page" data-testid="teacher-referrals-page">
      <PageHeader
        icon={Send}
        eyebrow={`مساحة ${roleLabel("TEACHER", schoolType)}`}
        title="إحالات الطلاب"
        description={`ابحث عن ${studentSingular} وأنشئ الإحالة؛ ستصل أولًا إلى وكيل الصف أو الفصل، ثم يحلها أو يحولها إلى ${counselorLabel}.`}
        tone="teacher"
        badge={list.isPending ? "جارٍ التحديث" : `${total} إحالة`}
        actions={(
          <Link to="/" className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-white/10 px-4 text-sm font-bold text-white ring-1 ring-white/15 transition hover:bg-white/15 sm:w-auto">
            <ArrowRight aria-hidden size={17} />
            العودة للتحضير
          </Link>
        )}
      />

      <section className="overflow-hidden rounded-3xl border border-teal-100 bg-white shadow-lg shadow-teal-950/5" aria-labelledby="new-referral-title">
        <div className="border-b border-teal-100 bg-gradient-to-l from-teal-50 to-white p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-teal-600 text-white shadow-sm">
              <UserRoundPlus aria-hidden size={21} />
            </span>
            <div>
              <h2 id="new-referral-title" className="text-lg font-black text-slate-900">إنشاء تحويل جديد</h2>
              <p className="mt-1 text-sm leading-6 text-slate-600">اختر {studentSingular} أولًا، ثم سجّل سبب الإحالة والملاحظة.</p>
            </div>
          </div>
        </div>

        <div className="space-y-5 p-4 sm:p-6">
          <form className="grid gap-3 lg:grid-cols-[minmax(14rem,2fr)_1fr_1fr_auto] lg:items-end" onSubmit={applySearch}>
            <label className="block text-sm font-bold text-slate-700">
              اسم {studentSingular}
              <span className="relative mt-1.5 block">
                <Search aria-hidden size={17} className="pointer-events-none absolute end-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="search"
                  value={searchInput}
                  onChange={(event) => {
                    setSearchInput(event.target.value);
                    setCandidatePage(1);
                    setSelectedStudent(null);
                  }}
                  placeholder={`ابحث باسم ${studentSingular}`}
                  className="min-h-11 w-full pe-10 ps-3"
                  data-testid="referral-student-search"
                />
                <span className="mt-1 block text-xs font-medium text-slate-500">
                  تتحدث النتائج تلقائيًا أثناء الكتابة.
                </span>
              </span>
            </label>
            <label className="block text-sm font-bold text-slate-700">
              الصف
              <select
                value={grade}
                onChange={(event) => {
                  setGrade(event.target.value);
                  setSection("");
                  setCandidatePage(1);
                  setSelectedStudent(null);
                }}
                className="mt-1.5 min-h-11 w-full"
                data-testid="referral-grade-filter"
              >
                <option value="">كل الصفوف</option>
                {grades.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
            <label className="block text-sm font-bold text-slate-700">
              الفصل
              <select
                value={section}
                onChange={(event) => {
                  setSection(event.target.value);
                  setCandidatePage(1);
                  setSelectedStudent(null);
                }}
                className="mt-1.5 min-h-11 w-full"
                data-testid="referral-section-filter"
              >
                <option value="">كل الفصول</option>
                {filteredSections.map((item) => (
                  <option key={item.id} value={item.id}>{item.grade_name} / {item.name}</option>
                ))}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-2 lg:flex">
              <Button type="submit" className="justify-center"><Search aria-hidden size={16} /> بحث</Button>
              <Button type="button" variant="secondary" className="justify-center" onClick={resetSearch} aria-label="مسح فلاتر البحث">
                <FilterX aria-hidden size={17} /> مسح
              </Button>
            </div>
          </form>

          {selectedStudent && (
            <ReferralCreateCard
              key={selectedStudent.id}
              student={{ id: selectedStudent.id, name: selectedStudent.full_name }}
              onCreated={(id) => finishReferral("تم إرسال الإحالة إلى الوكيل المسؤول، ويمكنك متابعة مسارها أدناه.", id)}
              onContributed={(id) => finishReferral("أضيفت ملاحظتك إلى ملف المتابعة المفتوح ويمكنك متابعته أدناه.", id)}
              onCancel={() => setSelectedStudent(null)}
            />
          )}

          {candidates.isPending && <Spinner label={`جارٍ تحميل ${studentPlural}...`} />}
          {candidates.isError && <ErrorState error={candidates.error} />}
          {candidates.isSuccess && candidates.data.results.length === 0 && (
            <EmptyState title={`لا يوجد ${studentSingular} مطابق`} description="غيّر الاسم أو اختر صفًا أو فصلًا آخر." compact />
          )}
          {candidates.isSuccess && candidates.data.results.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-bold text-slate-700">نتائج البحث</p>
                <p className="text-xs text-slate-500" aria-live="polite">{candidates.data.count} {studentSingular}</p>
              </div>
              <ul className="grid gap-2 md:grid-cols-2 xl:grid-cols-3" data-testid="referral-candidates">
                {candidates.data.results.map((student) => {
                  const isSelected = selectedStudent?.id === student.id;
                  return (
                    <li key={student.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setNotice(null);
                          setSelectedStudent(isSelected ? null : student);
                        }}
                        className={`flex min-h-20 w-full items-center justify-between gap-3 rounded-2xl border p-3 text-start transition ${isSelected ? "border-teal-500 bg-teal-50 ring-2 ring-teal-500/15" : "border-slate-200 bg-white hover:border-teal-300 hover:bg-slate-50"}`}
                        aria-pressed={isSelected}
                        data-testid={`referral-candidate-${student.id}`}
                      >
                        <span className="min-w-0">
                          <strong className="block break-words text-sm text-slate-900">{student.full_name}</strong>
                          <span className="mt-1 block text-xs text-slate-500">{student.grade.name} / {student.section.name}</span>
                        </span>
                        <span className={`shrink-0 rounded-lg px-2.5 py-1 text-xs font-bold ${isSelected ? "bg-teal-700 text-white" : "bg-teal-50 text-teal-800"}`}>
                          {isSelected ? "تم الاختيار" : "اختيار"}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
              <Pagination
                page={candidatePage}
                hasNext={Boolean(candidates.data.next)}
                hasPrevious={Boolean(candidates.data.previous)}
                onChange={(page: number) => {
                  setCandidatePage(page);
                  setSelectedStudent(null);
                }}
              />
            </div>
          )}
        </div>
      </section>

      {notice && <p role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-bold text-emerald-900" data-testid="referral-done">{notice}</p>}

      <section className="space-y-4" aria-labelledby="my-referrals-title">
        <div className="flex items-start gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-blue-50 text-blue-700"><GraduationCap aria-hidden size={21} /></span>
          <div>
            <h2 id="my-referrals-title" className="text-xl font-black text-slate-900">متابعة إحالاتي</h2>
            <p className="mt-1 text-sm text-slate-600">تابع مراجعة الوكيل، والتحويل للمرشد عند الحاجة، والإغلاق دون الاطلاع على إحالات زملائك.</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3" aria-label={`ملخص إحالات ${roleLabel("TEACHER", schoolType)}`}>
          <div className="rounded-2xl border border-blue-100 bg-blue-50/70 p-4">
            <Clock3 aria-hidden size={20} className="mb-3 text-blue-600" />
            <p className="text-2xl font-black text-slate-900">{summaryPending ? "—" : activeCount}</p>
            <p className="text-sm font-medium text-slate-600">قيد المتابعة</p>
          </div>
          <div className="rounded-2xl border border-emerald-100 bg-emerald-50/70 p-4">
            <CheckCircle2 aria-hidden size={20} className="mb-3 text-emerald-600" />
            <p className="text-2xl font-black text-slate-900">{summaryPending ? "—" : closedCount}</p>
            <p className="text-sm font-medium text-slate-600">مغلقة أو ملغاة</p>
          </div>
          <div className="col-span-2 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:col-span-1">
            <Send aria-hidden size={20} className="mb-3 text-slate-500" />
            <p className="text-2xl font-black text-slate-900">{list.isPending ? "—" : total}</p>
            <p className="text-sm font-medium text-slate-600">إجمالي إحالاتك</p>
          </div>
        </div>

        {list.isPending && <Spinner label="جارٍ تحميل الإحالات..." />}
        {list.isError && <ErrorState error={list.error} />}
        {list.isSuccess && (
          <>
            <ReferralsTable
              rows={rows}
              onSelect={(id) => setSelectedReferral(selectedReferral === id ? null : id)}
              selectedId={selectedReferral}
              emptyText="لم تنشئ أي إحالة بعد. ابحث عن الطالب من نموذج التحويل أعلاه."
              testId="my-referrals-rows"
              studentTitle={studentLabel(schoolType, true)}
            />
            <Pagination
              page={referralPage}
              hasNext={Boolean(list.data.next)}
              hasPrevious={Boolean(list.data.previous)}
              onChange={(page: number) => {
                setReferralPage(page);
                setSelectedReferral(null);
              }}
            />
          </>
        )}
      </section>

      {selectedReferral !== null && (
        <ReferralDetailCard
          referralId={selectedReferral}
          onChanged={() => {
            void queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "my-referrals") });
          }}
          onClose={() => setSelectedReferral(null)}
        />
      )}
    </div>
  );
}

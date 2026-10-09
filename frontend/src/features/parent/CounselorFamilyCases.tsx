import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Pagination } from "@/components/Pagination";
import { TextField } from "@/components/TextField";
import { schoolScopedKey } from "@/features/auth/useMe";
import { getCases } from "@/features/counseling/api";
import { useActiveSchoolId } from "@/features/settings/hooks";
import { surface } from "@/features/parent/shared";

export function CounselorFamilyCases() {
  const schoolId = useActiveSchoolId();
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => {
    if (search.trim() === appliedSearch) return;
    const timer = window.setTimeout(() => { setAppliedSearch(search.trim()); setPage(1); }, 350);
    return () => window.clearTimeout(timer);
  }, [search, appliedSearch]);
  const cases = useQuery({
    queryKey: schoolScopedKey(schoolId, "counselor-family-cases", appliedSearch, page),
    queryFn: ({ signal }) => getCases({ search: appliedSearch, page }, signal),
    enabled: schoolId > 0,
  });
  return (
    <section className={surface}>
      <h2 className="text-lg font-black">متابعة الأسرة من ملف الحالة</h2>
      <p className="mt-2 text-sm leading-7 text-slate-600">
        اختر الطالب لكتابة توصية ومتابعة اطلاع أسرته وتنفيذ الإجراء المطلوب.
      </p>
      <div className="mt-4">
        <TextField
          label="البحث باسم الطالب في حالاتي"
          type="search"
          maxLength={100}
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
          }}
        />
      </div>
      {cases.isError && <ErrorState error={cases.error} />}
      {cases.isPending && (
        <p className="mt-4" role="status">
          جارٍ تحميل الحالات…
        </p>
      )}
      {cases.data?.results.map((row) => (
        <Link
          key={row.id}
          to={`/counselor/cases/${row.id}?tab=family`}
          className="mt-3 flex min-h-11 flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 p-4 hover:bg-teal-50"
        >
          <span>
            <strong>{row.student_name}</strong>
            <span className="ms-2 text-sm text-slate-500">
              {row.grade_name} / {row.section_name} · {row.status_label}
            </span>
          </span>
          <span className="text-sm font-bold text-teal-800">
            فتح متابعة الأسرة
          </span>
        </Link>
      ))}
      {cases.data?.results.length === 0 && (
        <EmptyState
          title="لا توجد حالات مطابقة"
          description="ابحث باسم آخر أو راجع الحالات المسندة إليك."
        />
      )}
      <Pagination
        page={page}
        onChange={setPage}
        hasNext={!!cases.data?.next}
        hasPrevious={!!cases.data?.previous}
      />
    </section>
  );
}

import { useQuery } from "@tanstack/react-query";
import { ArrowUpLeft, CalendarClock, FileHeart, FolderOpen, UserRound } from "lucide-react";
import { Link } from "react-router-dom";

import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { CASE_IMPROVEMENT_LABELS, getStudentCounseling } from "@/features/counseling/api";
import { useActiveSchoolId, useActiveSchoolType } from "@/features/settings/hooks";

/** «الإرشاد والمتابعة» في ملف الطالب — ملخص بلا أي نص إرشادي (البنود 83-85).
 *  المعلم لا يصل إلى هذا التبويب أصلًا (الخادم يرد 403 والتبويب مخفي). */
export function StudentCounselingTab({ studentId }: { studentId: number }) {
  const schoolId = useActiveSchoolId();
  const schoolType = useActiveSchoolType();
  const me = useMe();
  const canOpenCase =
    me.data?.roles.some(
      (role) => role === "SCHOOL_MANAGER" || role === "VICE_PRINCIPAL" || role === "COUNSELOR",
    ) ?? false;

  const summary = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-counseling", studentId),
    queryFn: ({ signal }) => getStudentCounseling(studentId, signal),
    enabled: schoolId > 0 && canOpenCase,
  });

  if (!canOpenCase) return null;
  if (summary.isPending) return <Spinner />;
  if (summary.isError) return <ErrorState error={summary.error} />;

  const data = summary.data;
  if (!data) return null;

  return (
    <div className="space-y-4" data-testid="student-counseling-tab">
      <section
        className="overflow-hidden rounded-2xl border border-teal-100 bg-gradient-to-l from-teal-950 via-slate-900 to-indigo-950 text-white shadow-sm"
        data-testid="counseling-summary"
      >
        <div className="flex flex-wrap items-center justify-between gap-4 p-5">
          <div className="flex items-center gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-white/10 text-teal-200 ring-1 ring-white/10">
              <FileHeart aria-hidden size={21} />
            </span>
            <div>
              <h2 className="font-black">ملفات الإرشاد والمتابعة</h2>
              <p className="mt-1 text-xs leading-5 text-slate-300">
                نظرة موجزة على مسار {schoolType === "GIRLS" ? "الطالبة" : "الطالب"} دون إظهار الملاحظات المهنية الحساسة.
              </p>
            </div>
          </div>
          <div className="grid min-w-56 grid-cols-2 gap-2 text-center">
            <div className="rounded-xl bg-white/10 px-4 py-2.5 ring-1 ring-white/10">
              <span className="block text-2xl font-black text-teal-200">{data.open_cases}</span>
              <span className="text-[11px] font-bold text-slate-300">ملف مفتوح</span>
            </div>
            <div className="rounded-xl bg-white/10 px-4 py-2.5 ring-1 ring-white/10">
              <span className="block text-2xl font-black">{data.total_cases}</span>
              <span className="text-[11px] font-bold text-slate-300">إجمالي الملفات</span>
            </div>
          </div>
        </div>
        <p className="sr-only">
          ملفات متابعة مفتوحة: {data.open_cases} · الإجمالي: {data.total_cases}
        </p>
      </section>

      {data.cases.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center shadow-sm">
          <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-slate-100 text-slate-500">
            <FolderOpen aria-hidden size={22} />
          </span>
          <p className="mt-3 font-bold text-slate-800">لا توجد ملفات متابعة إرشادية {schoolType === "GIRLS" ? "لهذه الطالبة" : "لهذا الطالب"}.</p>
          <p className="mt-1 text-xs text-slate-500">ستظهر الحالات هنا بعد فتحها من صندوق الإحالات.</p>
        </div>
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {data.cases.map((row) => (
            <li
              key={row.id}
              className="group rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-teal-200 hover:shadow-md"
              data-testid={`counseling-case-${row.id}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-teal-50 text-teal-700">
                    <FolderOpen aria-hidden size={19} />
                  </span>
                  <div>
                    <span className="inline-flex rounded-full bg-teal-50 px-2.5 py-1 text-xs font-black text-teal-800 ring-1 ring-teal-100">
                      {row.status_label}
                    </span>
                    <p className="mt-2 flex items-center gap-1.5 text-xs text-slate-500">
                      <CalendarClock aria-hidden size={14} />
                      فُتح: {row.opened_at}
                      {row.closed_at ? ` · أُغلق: ${row.closed_at}` : ""}
                    </p>
                  </div>
                </div>
                <Link
                  to={`/counselor/cases/${row.id}`}
                  className="inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-xl bg-slate-950 px-3 py-2 text-xs font-bold text-white transition hover:bg-teal-900 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-teal-500/20"
                  data-testid={`open-counseling-case-${row.id}`}
                >
                  فتح الملف
                  <ArrowUpLeft aria-hidden size={15} />
                </Link>
              </div>
              <div className="mt-4 grid gap-2 border-t border-slate-100 pt-3 text-xs sm:grid-cols-2">
                <p className="flex items-center gap-2 rounded-xl bg-slate-50 px-3 py-2.5 text-slate-600">
                  <UserRound aria-hidden size={15} className="text-slate-400" />
                  <span><span className="block text-[10px] text-slate-400">المرشد</span><strong className="text-slate-800">{row.counselor_name ?? "—"}</strong></span>
                </p>
                <p className="rounded-xl bg-slate-50 px-3 py-2.5 text-slate-600">
                  <span className="block text-[10px] text-slate-400">آخر متابعة</span>
                  <strong className="text-slate-800">{row.last_activity_at}</strong>
                </p>
              </div>
              {row.improvement_status && (
                <p className="mt-3 rounded-xl bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-800 ring-1 ring-emerald-100">
                  نتيجة المتابعة: {CASE_IMPROVEMENT_LABELS[row.improvement_status] ?? row.improvement_status}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

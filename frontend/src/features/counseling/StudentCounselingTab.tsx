import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { CASE_IMPROVEMENT_LABELS, getStudentCounseling } from "@/features/counseling/api";
import { useActiveSchoolId } from "@/features/settings/hooks";

/** «الإرشاد والمتابعة» في ملف الطالب — ملخص بلا أي نص إرشادي (البنود 83-85).
 *  المعلم لا يصل إلى هذا التبويب أصلًا (الخادم يرد 403 والتبويب مخفي). */
export function StudentCounselingTab({ studentId }: { studentId: number }) {
  const schoolId = useActiveSchoolId();
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
    <div className="space-y-3" data-testid="student-counseling-tab">
      <p className="text-sm text-slate-700" data-testid="counseling-summary">
        ملفات متابعة مفتوحة: {data.open_cases} · الإجمالي: {data.total_cases}
      </p>

      {data.cases.length === 0 ? (
        <p className="rounded-xl border border-slate-200 bg-white p-6 text-slate-600 shadow-sm">
          لا توجد ملفات متابعة إرشادية لهذا الطالب.
        </p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white shadow-sm">
          {data.cases.map((row) => (
            <li key={row.id} className="space-y-1 p-4" data-testid={`counseling-case-${row.id}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold">{row.status_label}</span>
                <span className="text-sm text-slate-600">
                  فُتح: {row.opened_at}
                  {row.closed_at ? ` · أُغلق: ${row.closed_at}` : ""}
                </span>
              </div>
              <p className="text-sm text-slate-600">
                المرشد: {row.counselor_name ?? "—"} · آخر متابعة: {row.last_activity_at}
                {row.improvement_status
                  ? ` · النتيجة: ${CASE_IMPROVEMENT_LABELS[row.improvement_status] ?? row.improvement_status}`
                  : ""}
              </p>
              <Link
                to={`/counselor/cases/${row.id}`}
                className="text-sm text-blue-700 underline"
                data-testid={`open-counseling-case-${row.id}`}
              >
                فتح ملف المتابعة
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

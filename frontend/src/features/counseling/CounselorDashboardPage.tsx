import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { getCases, getCounselorDashboard } from "@/features/counseling/api";
import { useActiveSchoolId } from "@/features/settings/hooks";

const KPI_CARDS: { key: keyof import("@/features/counseling/api").DashboardKpis; label: string }[] = [
  { key: "new_referrals", label: "إحالات جديدة" },
  { key: "open_cases", label: "حالات مفتوحة" },
  { key: "under_assessment", label: "قيد الدراسة" },
  { key: "follow_up_active", label: "تحت المتابعة" },
  { key: "waiting_teacher_response", label: "بانتظار رد معلم" },
  { key: "due_activities", label: "إجراءات مستحقة" },
  { key: "closed_this_month", label: "أغلقت هذا الشهر" },
];

const CATEGORIES: Record<string, string> = {
  ATTENDANCE: "المواظبة",
  ACADEMIC: "الأداء الدراسي",
  CLASSROOM_BEHAVIOR: "سلوك صفي",
  SOCIAL: "اجتماعي",
  OTHER: "أخرى",
};

/** لوحة المرشد: مؤشرات + قائمة الحالات بفلاترها وترتيبها (البنود 56-61). */
export function CounselorDashboardPage() {
  const schoolId = useActiveSchoolId();
  const me = useMe();
  const [status, setStatus] = useState("live");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState("recent");
  const [page, setPage] = useState(1);

  const kpis = useQuery({
    queryKey: schoolScopedKey(schoolId, "counselor-dashboard"),
    queryFn: ({ signal }) => getCounselorDashboard(signal),
    enabled: schoolId > 0,
  });
  const cases = useQuery({
    queryKey: schoolScopedKey(schoolId, "counselor-cases", status, category, sort, page),
    queryFn: ({ signal }) => getCases({ status, category, sort, page }, signal),
    enabled: schoolId > 0,
  });

  if (me.isPending || kpis.isPending) return <Spinner />;
  if (kpis.isError) return <ErrorState error={kpis.error} />;

  const rows = cases.data?.results ?? [];
  const count = cases.data?.count ?? 0;

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">لوحة الإرشاد الطلابي</h1>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="counselor-kpis">
        {KPI_CARDS.map((card) => (
          <div
            key={card.key}
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
            data-testid={`kpi-${card.key}`}
          >
            <p className="text-sm text-slate-600">{card.label}</p>
            <p className="text-2xl font-bold">{kpis.data?.[card.key] ?? 0}</p>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <label className="flex flex-col gap-1 text-sm">
          الحالة
          <select
            data-testid="case-status-filter"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="live">الحالات الحية</option>
            <option value="OPEN">مفتوحة</option>
            <option value="UNDER_ASSESSMENT">قيد الدراسة</option>
            <option value="FOLLOW_UP_ACTIVE">متابعة جارية</option>
            <option value="RESOLVED">تم التحسن</option>
            <option value="CLOSED">مغلقة</option>
            <option value="">الكل</option>
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          الفئة
          <select
            data-testid="case-category-filter"
            value={category}
            onChange={(event) => {
              setCategory(event.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">كل الفئات</option>
            {Object.entries(CATEGORIES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          الترتيب
          <select
            data-testid="case-sort"
            value={sort}
            onChange={(event) => setSort(event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="recent">الأحدث نشاطًا</option>
            <option value="oldest_unattended">الأقدم بلا متابعة</option>
            <option value="opened">الأحدث فتحًا</option>
          </select>
        </label>
      </div>

      {cases.isError && <ErrorState error={cases.error} />}
      {cases.isPending ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <p
          className="rounded-xl border border-slate-200 bg-white p-6 text-slate-600 shadow-sm"
          data-testid="no-cases"
        >
          لا توجد حالات مطابقة.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="p-3 text-start">الطالب</th>
                <th className="p-3 text-start">الصف/الفصل</th>
                <th className="p-3 text-start">سبب الإحالة</th>
                <th className="p-3 text-start">المرشد</th>
                <th className="p-3 text-start">الحالة</th>
                <th className="p-3 text-start">آخر نشاط</th>
                <th className="p-3 text-start">الإجراء القادم</th>
                <th className="p-3 text-start"></th>
              </tr>
            </thead>
            <tbody data-testid="cases-table">
              {rows.map((row) => (
                <tr key={row.id} className="border-b" data-testid={`case-row-${row.id}`}>
                  <td className="p-3">{row.student_name}</td>
                  <td className="p-3">
                    {row.grade_name ?? "—"} / {row.section_name ?? "—"}
                  </td>
                  <td className="p-3">{row.referral_reason_label}</td>
                  <td className="p-3">{row.counselor_name ?? "—"}</td>
                  <td className="p-3">{row.status_label}</td>
                  <td className="p-3">{row.last_activity_at.slice(0, 10)}</td>
                  <td className="p-3">{row.next_activity_due ?? "—"}</td>
                  <td className="p-3">
                    <Link
                      to={`/counselor/cases/${row.id}`}
                      className="text-blue-700 underline"
                      data-testid={`open-case-${row.id}`}
                    >
                      فتح الملف
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {count > rows.length && (
        <div className="flex items-center gap-3 text-sm">
          <button
            type="button"
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            disabled={page === 1}
            className="rounded-lg border border-slate-300 px-3 py-1 disabled:opacity-50"
          >
            السابق
          </button>
          <span>
            صفحة {page} — الإجمالي {count}
          </span>
          <button
            type="button"
            onClick={() => setPage((value) => value + 1)}
            disabled={rows.length === 0}
            className="rounded-lg border border-slate-300 px-3 py-1 disabled:opacity-50"
          >
            التالي
          </button>
        </div>
      )}
    </div>
  );
}

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleDot, Filter, Inbox, Send, UserRoundCheck } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { MetricCard } from "@/components/MetricCard";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import {
  type ReferralFilters,
  type ReferralRow,
  getReferralKpis,
  getReferralOptions,
  getReferrals,
} from "@/features/referrals/api";
import { ReferralDetailCard } from "@/features/referrals/ReferralDetailCard";
import { useActiveSchoolId } from "@/features/settings/hooks";
import { roleLabel, studentLabel } from "@/utils/roles";

const READ_ROLES = ["SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR"];

export function ReferralStatusBadge({
  status,
  label,
}: {
  status: string;
  label: string;
}) {
  const tone =
    status === "ACKNOWLEDGED"
      ? "bg-blue-100 text-blue-800"
      : status === "CLOSED"
        ? "bg-emerald-100 text-emerald-800"
        : status === "CANCELLED"
          ? "bg-slate-200 text-slate-700"
          : "bg-amber-100 text-amber-900";
  return <span className={`rounded-full px-2 py-1 text-xs ${tone}`}>{label}</span>;
}

export function ReferralsTable({
  rows,
  onSelect,
  selectedId,
  emptyText,
  testId,
  studentTitle = "الطالب",
}: {
  rows: ReferralRow[];
  onSelect: (id: number) => void;
  selectedId?: number | null;
  emptyText: string;
  testId: string;
  studentTitle?: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <table className="block w-full text-sm md:table">
        <thead className="hidden md:table-header-group">
          <tr className="border-b border-slate-200 bg-slate-50/80 text-slate-500">
            <th className="p-3 text-start">{studentTitle}</th>
            <th className="p-3 text-start">الصف/الفصل</th>
            <th className="p-3 text-start">المصدر</th>
            <th className="p-3 text-start">السبب</th>
            <th className="p-3 text-start">المُحيل</th>
            <th className="p-3 text-start">المرشد</th>
            <th className="p-3 text-start">الحالة</th>
            <th className="p-3 text-start"></th>
          </tr>
        </thead>
        <tbody className="grid gap-3 p-3 md:table-row-group md:p-0" data-testid={testId}>
          {rows.map((row) => (
            <tr key={row.id} className="grid grid-cols-2 gap-3 rounded-2xl border border-slate-200 p-4 transition-colors hover:bg-slate-50/70 md:table-row md:border-x-0 md:border-t-0 md:p-0" data-testid={`referral-row-${row.id}`}>
              <td className="col-span-2 p-0 font-bold text-slate-800 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">{studentTitle}</span>{row.student.full_name}</td>
              <td className="p-0 md:table-cell md:p-3">
                <span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">الصف/الفصل</span>
                {row.student.grade_name ?? "—"} / {row.student.section_name ?? "—"}
              </td>
              <td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">المصدر</span>{row.source_type_label}</td>
              <td className="col-span-2 p-0 md:table-cell md:p-3">
                <span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">السبب</span>
                {row.category_label}
                <span className="block text-xs text-slate-500">{row.reason_label}</span>
              </td>
              <td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">المُحيل</span>{row.created_by_name ?? "—"}</td>
              <td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">المرشد</span>{row.assigned_counselor_name ?? "غير معيّن"}</td>
              <td className="p-0 md:table-cell md:p-3">
                <span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">الحالة</span>
                <ReferralStatusBadge status={row.status} label={row.status_label} />
              </td>
              <td className="col-span-2 p-0 md:table-cell md:p-3">
                <button
                  type="button"
                  className="min-h-10 w-full rounded-xl bg-blue-50 px-3 font-bold text-blue-700 transition hover:bg-blue-100 md:w-auto"
                  onClick={() => onSelect(row.id)}
                  data-testid={`open-referral-${row.id}`}
                  aria-expanded={selectedId === row.id}
                  aria-controls="referral-details"
                >
                  التفاصيل
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && (
        <div className="p-4"><EmptyState title="لا توجد إحالات" description={emptyText} testId="no-referrals" compact /></div>
      )}
    </div>
  );
}

/** صندوق وارد الإحالات — للمرشد والإدارة (بند 50). لا تحليلات ولا خطط متابعة. */
export function ReferralsPage() {
  const me = useMe();
  const schoolId = useActiveSchoolId();
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<ReferralFilters>({ page: 1 });
  const [selected, setSelected] = useState<number | null>(null);

  const canRead = me.data?.roles.some((role) => READ_ROLES.includes(role)) ?? true;

  const kpis = useQuery({
    queryKey: schoolScopedKey(schoolId, "referral-kpis"),
    queryFn: ({ signal }) => getReferralKpis(signal),
    enabled: schoolId > 0 && canRead,
  });
  const options = useQuery({
    queryKey: schoolScopedKey(schoolId, "referral-options"),
    queryFn: ({ signal }) => getReferralOptions(signal),
    enabled: schoolId > 0 && canRead,
  });
  const list = useQuery({
    queryKey: schoolScopedKey(schoolId, "referrals", JSON.stringify(filters)),
    queryFn: ({ signal }) => getReferrals(filters, signal),
    enabled: schoolId > 0 && canRead,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "referrals") });
    queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "referral-kpis") });
  };

  if (me.isSuccess && !canRead) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <h2 className="mb-2 text-lg font-bold">لا تملك صلاحية عرض الإحالات</h2>
        <p className="text-slate-600">
          صندوق الإحالات متاح لكل من {roleLabel("COUNSELOR", schoolType)} و{roleLabel("SCHOOL_MANAGER", schoolType)} و{roleLabel("VICE_PRINCIPAL", schoolType)}. {roleLabel("TEACHER", schoolType)} يرى إحالاته من
          صفحة «إحالاتي».
        </p>
      </section>
    );
  }
  if (list.isError) return <ErrorState error={list.error} />;

  const setFilter = (key: keyof ReferralFilters, value: string) =>
    setFilters((current) => ({ ...current, [key]: value || undefined, page: 1 }));

  return (
    <div className="space-y-5">
      <PageHeader
        icon={Send}
        eyebrow="صندوق المتابعة المشترك"
        title="الإحالات"
        description="متابعة الإحالات الواردة وتعيينها للمرشد وتوثيق مسار التعامل معها حتى الإغلاق."
        tone={me.data?.roles.includes("COUNSELOR") ? "counselor" : "operational"}
        badge={me.data?.roles.includes("COUNSELOR") ? roleLabel("COUNSELOR", schoolType) : "فريق الإدارة"}
      />

      <div className="grid grid-cols-3 gap-2" data-testid="referral-kpis">
        <MetricCard label="جديدة" value={kpis.data?.new_count ?? 0} icon={Inbox} tone="blue" />
        <MetricCard label="تم استلامها" value={kpis.data?.acknowledged_count ?? 0} icon={UserRoundCheck} tone="teal" />
        <MetricCard label="غير معينة" value={kpis.data?.unassigned_count ?? 0} icon={CircleDot} tone="amber" />
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center gap-2"><Filter aria-hidden size={18} className="text-slate-500" /><h2 className="font-black text-slate-900">تصفية صندوق الإحالات</h2></div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="flex flex-col gap-1 text-sm">
          الحالة
          <select
            data-testid="filter-status"
            onChange={(event) => setFilter("status", event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">الكل</option>
            <option value="OPEN">المفتوحة</option>
            <option value="NEW">جديدة</option>
            <option value="ACKNOWLEDGED">تم الاستلام</option>
            <option value="CLOSED">مغلقة</option>
            <option value="CANCELLED">ملغاة</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          الفئة
          <select
            data-testid="filter-category"
            onChange={(event) => setFilter("category", event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">الكل</option>
            {(options.data?.categories ?? []).map((category) => (
              <option key={category.value} value={category.value}>
                {category.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          المصدر
          <select
            data-testid="filter-source"
            onChange={(event) => setFilter("source_type", event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">الكل</option>
            <option value="TEACHER">{roleLabel("TEACHER", schoolType)}</option>
            <option value="VICE_PRINCIPAL">{roleLabel("VICE_PRINCIPAL", schoolType)}</option>
            <option value="SCHOOL_MANAGER">{roleLabel("SCHOOL_MANAGER", schoolType)}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          التعيين
          <select
            data-testid="filter-counselor"
            onChange={(event) => setFilter("counselor", event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">الكل</option>
            <option value="UNASSIGNED">غير معينة</option>
          </select>
        </label>
        </div>
      </section>

      {list.isPending ? (
        <Spinner />
      ) : (
        <ReferralsTable
          rows={list.data?.results ?? []}
          onSelect={(id) => setSelected(selected === id ? null : id)}
          selectedId={selected}
          emptyText="لا توجد إحالات مطابقة."
          testId="referrals-rows"
          studentTitle={studentLabel(schoolType, true)}
        />
      )}

      {selected !== null && (
        <ReferralDetailCard
          referralId={selected}
          onChanged={refresh}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

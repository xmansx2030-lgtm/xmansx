import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import {
  type ExcuseFilters,
  REASON_LABELS,
  getExcuseKpis,
  getExcuses,
} from "@/features/excuses/api";
import { ExcuseCreateCard } from "@/features/excuses/ExcuseCreateCard";
import { ExcuseDetailCard } from "@/features/excuses/ExcuseDetailCard";
import { useActiveSchoolId } from "@/features/settings/hooks";

const READ_ROLES = ["SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR"];
const MANAGE_ROLES = ["SCHOOL_MANAGER", "VICE_PRINCIPAL"];

export function formatDate(value: string) {
  return new Intl.DateTimeFormat("ar-SA", { dateStyle: "medium" }).format(
    new Date(`${value}T12:00:00`),
  );
}

export function ExcusesPage() {
  const me = useMe();
  const schoolId = useActiveSchoolId();
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<ExcuseFilters>({ page: 1 });
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);

  const canRead = me.data?.roles.some((role) => READ_ROLES.includes(role)) ?? true;
  const canManage = me.data?.roles.some((role) => MANAGE_ROLES.includes(role)) ?? false;

  const kpis = useQuery({
    queryKey: schoolScopedKey(schoolId, "excuse-kpis"),
    queryFn: ({ signal }) => getExcuseKpis(signal),
    enabled: schoolId > 0 && canRead,
  });
  const list = useQuery({
    queryKey: schoolScopedKey(schoolId, "excuses", JSON.stringify(filters)),
    queryFn: ({ signal }) => getExcuses(filters, signal),
    enabled: schoolId > 0 && canRead,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "excuses") });
    queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, "excuse-kpis") });
  };

  if (me.isSuccess && !canRead) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <h2 className="mb-2 text-lg font-bold">لا تملك صلاحية عرض الأعذار</h2>
        <p className="text-slate-600">إدارة الأعذار متاحة لمدير المدرسة والوكيل.</p>
      </section>
    );
  }
  if (list.isError) return <ErrorState error={list.error} />;

  const setFilter = (key: keyof ExcuseFilters, value: string) =>
    setFilters((current) => ({ ...current, [key]: value || undefined, page: 1 }));

  const totalPages = Math.max(1, Math.ceil((list.data?.count ?? 0) / 25));
  const page = filters.page ?? 1;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">الأعذار</h1>
        {canManage && (
          <Button onClick={() => setCreating((value) => !value)} data-testid="new-excuse">
            {creating ? "إغلاق" : "إضافة عذر"}
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" data-testid="excuse-kpis">
        <Kpi label="بانتظار الاعتماد" value={kpis.data?.pending_count ?? 0} />
        <Kpi label="معتمدة اليوم" value={kpis.data?.approved_today_count ?? 0} />
        <Kpi label="مرفوضة" value={kpis.data?.rejected_count ?? 0} />
        <Kpi label="ملغاة" value={kpis.data?.cancelled_count ?? 0} />
      </div>

      {creating && canManage && (
        <ExcuseCreateCard
          onCreated={(id) => {
            setCreating(false);
            setSelected(id);
            refresh();
          }}
          onCancel={() => setCreating(false)}
        />
      )}

      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <label className="flex flex-col gap-1 text-sm">
          الحالة
          <select
            data-testid="filter-status"
            onChange={(event) => setFilter("status", event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">الكل</option>
            <option value="PENDING">بانتظار الاعتماد</option>
            <option value="APPROVED">معتمد</option>
            <option value="REJECTED">مرفوض</option>
            <option value="CANCELLED">ملغى</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          نوع العذر
          <select
            data-testid="filter-reason"
            onChange={(event) => setFilter("reason_type", event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">الكل</option>
            {Object.entries(REASON_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          من تاريخ
          <input
            type="date"
            data-testid="filter-from"
            onChange={(event) => setFilter("from_date", event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          إلى تاريخ
          <input
            type="date"
            data-testid="filter-to"
            onChange={(event) => setFilter("to_date", event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
      </div>

      {list.isPending ? (
        <Spinner />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-slate-500">
                <th className="p-3 text-start">الطالب</th>
                <th className="p-3 text-start">الفترة</th>
                <th className="p-3 text-start">نوع العذر</th>
                <th className="p-3 text-start">الحالة</th>
                <th className="p-3 text-start">الحصص المغطاة</th>
                <th className="p-3 text-start">المسجل</th>
                <th className="p-3 text-start"></th>
              </tr>
            </thead>
            <tbody data-testid="excuses-rows">
              {(list.data?.results ?? []).map((row) => (
                <tr key={row.id} className="border-b" data-testid={`excuse-row-${row.id}`}>
                  <td className="p-3">
                    <strong>{row.student.full_name}</strong>
                    <span className="block text-xs text-slate-500">
                      {row.student.grade_name ?? "—"} / {row.student.section_name ?? "—"}
                    </span>
                  </td>
                  <td className="p-3">
                    {row.date_from
                      ? row.date_from === row.date_to
                        ? formatDate(row.date_from)
                        : `${formatDate(row.date_from)} — ${formatDate(row.date_to!)}`
                      : "—"}
                  </td>
                  <td className="p-3">{row.reason_type_label}</td>
                  <td className="p-3">
                    <StatusBadge status={row.status} label={row.status_label} />
                  </td>
                  <td className="p-3">{row.active_coverage_count} حصة</td>
                  <td className="p-3">{row.recorded_by_name ?? "—"}</td>
                  <td className="p-3">
                    <button
                      type="button"
                      className="text-blue-700 underline"
                      data-testid={`open-excuse-${row.id}`}
                      onClick={() => setSelected(selected === row.id ? null : row.id)}
                    >
                      التفاصيل
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(list.data?.results.length ?? 0) === 0 && (
            <p className="p-6 text-sm text-slate-500" data-testid="no-excuses">
              لا توجد أعذار مطابقة.
            </p>
          )}
          <div className="flex items-center justify-between border-t border-slate-100 p-3 text-sm">
            <span className="text-slate-500">
              صفحة {page} من {totalPages}
            </span>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                disabled={page <= 1}
                onClick={() => setFilters((f) => ({ ...f, page: page - 1 }))}
              >
                السابق
              </Button>
              <Button
                variant="secondary"
                disabled={page >= totalPages}
                onClick={() => setFilters((f) => ({ ...f, page: page + 1 }))}
              >
                التالي
              </Button>
            </div>
          </div>
        </div>
      )}

      {selected !== null && (
        <ExcuseDetailCard
          excuseId={selected}
          canManage={canManage}
          onChanged={refresh}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

export function StatusBadge({ status, label }: { status: string; label: string }) {
  const tone =
    status === "APPROVED"
      ? "bg-emerald-100 text-emerald-800"
      : status === "REJECTED"
        ? "bg-red-100 text-red-800"
        : status === "CANCELLED"
          ? "bg-slate-200 text-slate-700"
          : "bg-amber-100 text-amber-900";
  return <span className={`rounded-full px-2 py-1 text-xs ${tone}`}>{label}</span>;
}

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 text-center shadow-sm">
      <p className="text-xs text-slate-500">{label}</p>
      <strong className="mt-1 block text-2xl font-bold text-slate-800">{value}</strong>
    </div>
  );
}

export function useExcuseMutation<TArgs extends unknown[], TResult>(
  fn: (...args: TArgs) => Promise<TResult>,
  onDone: () => void,
) {
  return useMutation({ mutationFn: (args: TArgs) => fn(...args), onSuccess: onDone });
}

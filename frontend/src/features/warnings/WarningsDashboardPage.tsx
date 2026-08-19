import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import type { EligibilityRow, WarningLevel, WarningType } from "@/features/warnings/api";
import {
  LEVEL_LABELS,
  WARNING_TYPE_LABELS,
  WARNING_TYPE_UNITS,
  getEligibility,
  issueWarning,
} from "@/features/warnings/api";

const TYPES: WarningType[] = ["UNEXCUSED_FULL_DAY_ABSENCE", "MORNING_LATE_OCCURRENCES"];

/** «يحتاج متابعة» — الاكتشاف تلقائي والإصدار قرار صريح من الوكيل/المدير. */
export function WarningsDashboardPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const schoolId = me.data?.active_school?.id ?? 0;
  const [type, setType] = useState<WarningType | "">("");
  const [grade, setGrade] = useState<number | "">("");
  const [status, setStatus] = useState<"due" | "issued" | "all">("due");
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [issuedMessage, setIssuedMessage] = useState<string | null>(null);

  const eligibility = useQuery({
    queryKey: schoolScopedKey(schoolId, "warnings", "eligibility", type, grade, status, page),
    queryFn: ({ signal }) =>
      getEligibility({ warning_type: type, grade, status, page }, signal),
    enabled: schoolId > 0,
  });

  const grades = useMemo(() => {
    const map = new Map<number, string>();
    for (const row of eligibility.data?.results ?? []) map.set(row.grade_id, row.grade_name);
    return [...map.entries()];
  }, [eligibility.data?.results]);

  const issue = (row: EligibilityRow, level: WarningLevel) => {
    const key = `${row.student_id}-${row.warning_type}-${level}`;
    setPending(key);
    setError(null);
    setIssuedMessage(null);
    void issueWarning({
      student_id: row.student_id,
      warning_type: row.warning_type,
      level,
    })
      .then((warning) => {
        setIssuedMessage(
          `صدر ${warning.level_label} للطالب ${warning.student_name} عند ${warning.metric_value_at_issue}.`,
        );
        return queryClient.invalidateQueries({
          predicate: (q) => JSON.stringify(q.queryKey).includes('"warnings"'),
        });
      })
      .catch(setError)
      .finally(() => setPending(null));
  };

  if (eligibility.isPending) return <Spinner label="جارٍ حساب الاستحقاق..." />;
  if (eligibility.isError) return <ErrorState error={eligibility.error} />;
  const data = eligibility.data;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-lg font-bold text-slate-800">يحتاج متابعة — الإنذارات</h2>
        <p className="text-sm text-slate-500">
          النظام يكتشف بلوغ الحدود تلقائيًا، والإصدار يبقى قرارك. العام:{" "}
          {data.academic_year.name}
        </p>
      </section>

      <section className="grid grid-cols-1 gap-2 sm:grid-cols-2" data-testid="warning-kpis">
        {TYPES.map((current) => (
          <div
            key={current}
            data-testid={`kpi-${current}`}
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <p className="text-2xl font-bold text-slate-800">
              {data.summary[current]?.due_students ?? 0}
            </p>
            <p className="text-sm text-slate-600">
              طلاب وصلوا إلى حد {WARNING_TYPE_LABELS[current]}
            </p>
            <p className="text-xs text-slate-400">
              صدرت لهم إنذارات: {data.summary[current]?.issued_students ?? 0}
            </p>
          </div>
        ))}
      </section>

      <section className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <label className="text-sm text-slate-600">
          النوع{" "}
          <select
            value={type}
            onChange={(e) => {
              setType(e.target.value as WarningType | "");
              setPage(1);
            }}
            className="rounded-lg border border-slate-300 px-2 py-1.5"
            data-testid="type-filter"
          >
            <option value="">الكل</option>
            {TYPES.map((current) => (
              <option key={current} value={current}>
                {WARNING_TYPE_LABELS[current]}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-slate-600">
          الصف{" "}
          <select
            value={grade}
            onChange={(e) => {
              setGrade(e.target.value === "" ? "" : Number(e.target.value));
              setPage(1);
            }}
            className="rounded-lg border border-slate-300 px-2 py-1.5"
            data-testid="grade-filter"
          >
            <option value="">الكل</option>
            {grades.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-slate-600">
          الحالة{" "}
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as "due" | "issued" | "all");
              setPage(1);
            }}
            className="rounded-lg border border-slate-300 px-2 py-1.5"
            data-testid="status-filter"
          >
            <option value="due">مستحق</option>
            <option value="issued">صدر له إنذار</option>
            <option value="all">الكل</option>
          </select>
        </label>
      </section>

      {error != null && <ErrorState error={error} />}
      {issuedMessage && (
        <p
          className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-800"
          data-testid="issue-result"
        >
          {issuedMessage}
        </p>
      )}

      <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
        {data.results.length === 0 ? (
          <p className="p-6 text-slate-600" data-testid="no-due-students">
            لا يوجد طلاب ضمن هذا الفلتر.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100" data-testid="eligibility-list">
            {data.results.map((row) => {
              const key = `${row.student_id}-${row.warning_type}`;
              return (
                <li key={key} className="space-y-2 p-3" data-testid={`row-${key}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="font-medium text-slate-800">{row.full_name}</p>
                      <p className="text-xs text-slate-500">
                        {row.grade_name} / {row.section_name}
                      </p>
                    </div>
                    <p className="text-sm text-slate-700">
                      {WARNING_TYPE_LABELS[row.warning_type]}:{" "}
                      <span className="font-bold">{row.current_value}</span>{" "}
                      {WARNING_TYPE_UNITS[row.warning_type]}
                    </p>
                    <p className="text-sm text-slate-600">
                      وصل:{" "}
                      {row.highest_reached_level
                        ? LEVEL_LABELS[row.highest_reached_level]
                        : "—"}
                      {row.issued_levels.length > 0 && (
                        <span className="ms-2">
                          صدر: {row.issued_levels.map((l) => LEVEL_LABELS[l]).join("، ")}
                        </span>
                      )}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {(Object.entries(row.levels) as [WarningLevel, { threshold: number; state: string }][])
                      .filter(([, info]) => info.state === "DUE")
                      .map(([level, info]) => (
                        <Button
                          key={level}
                          disabled={!row.is_enabled || pending === `${key}-${level}`}
                          onClick={() => issue(row, level)}
                          data-testid={`issue-${key}-${level}`}
                        >
                          إصدار {LEVEL_LABELS[level]} (الحد {info.threshold})
                        </Button>
                      ))}
                    {!row.is_enabled && (
                      <span className="text-xs text-amber-700">
                        هذا النوع غير مفعّل في الإعدادات.
                      </span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {data.count > data.page_size && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            السابق
          </Button>
          <span>
            صفحة {page} من {Math.ceil(data.count / data.page_size)}
          </span>
          <Button
            variant="secondary"
            disabled={page * data.page_size >= data.count}
            onClick={() => setPage(page + 1)}
          >
            التالي
          </Button>
        </div>
      )}
    </div>
  );
}

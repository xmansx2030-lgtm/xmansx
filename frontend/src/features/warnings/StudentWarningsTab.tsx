import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import {
  WARNING_TYPE_UNITS,
  getStudentWarnings,
  getWarningDetail,
  voidWarning,
} from "@/features/warnings/api";

/** تبويب الإنذارات في ملف الطالب — القيمة وقت الإصدار منفصلة عن القيمة الحالية. */
export function StudentWarningsTab({ studentId }: { studentId: number }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const schoolId = me.data?.active_school?.id ?? 0;
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const canVoid = me.data?.roles.includes("SCHOOL_MANAGER") ?? false;
  const [openId, setOpenId] = useState<number | null>(null);
  const [voidReason, setVoidReason] = useState("");
  const [error, setError] = useState<unknown>(null);

  const list = useQuery({
    queryKey: schoolScopedKey(schoolId, "warnings", "student", studentId),
    queryFn: ({ signal }) => getStudentWarnings(studentId, signal),
    enabled: schoolId > 0,
  });

  const detail = useQuery({
    queryKey: schoolScopedKey(schoolId, "warnings", "detail", openId),
    queryFn: ({ signal }) => getWarningDetail(openId as number, signal),
    enabled: openId !== null,
  });

  const rows = list.data?.results ?? [];
  const absenceCount = rows.filter(
    (row) => row.warning_type === "UNEXCUSED_FULL_DAY_ABSENCE" && row.status === "ISSUED",
  ).length;
  const morningCount = rows.filter(
    (row) => row.warning_type === "MORNING_LATE_OCCURRENCES" && row.status === "ISSUED",
  ).length;

  if (list.isPending) return <Spinner />;
  if (list.isError) return <ErrorState error={list.error} />;

  return (
    <div className="space-y-3" data-testid="student-warnings-tab">
      <p className="text-sm text-slate-700" data-testid="warnings-summary">
        إنذارات الغياب: {absenceCount} · إنذارات التأخر: {morningCount}
      </p>
      {error != null && <ErrorState error={error} />}

      {rows.length === 0 ? (
        <p className="rounded-xl border border-slate-200 bg-white p-6 text-slate-600 shadow-sm">
          لا توجد إنذارات صادرة {schoolType === "GIRLS" ? "لهذه الطالبة" : "لهذا الطالب"}.
        </p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white shadow-sm">
          {rows.map((row) => (
            <li key={row.id} className="p-3" data-testid={`warning-${row.id}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-medium text-slate-800">
                    {row.level_label} — {row.warning_type_label}
                  </p>
                  <p className="text-xs text-slate-500">
                    {new Date(row.issued_at).toLocaleDateString("ar-SA")} · صدر عند{" "}
                    {row.metric_value_at_issue}{" "}
                    {WARNING_TYPE_UNITS[row.warning_type]} (الحد {row.threshold_at_issue})
                    {row.issued_by && ` · بواسطة ${row.issued_by}`}
                  </p>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-sm ${
                    row.status === "ISSUED"
                      ? "bg-green-100 text-green-800"
                      : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {row.status === "ISSUED" ? "صادر" : "ملغى"}
                </span>
                <Button
                  variant="secondary"
                  onClick={() => setOpenId(openId === row.id ? null : row.id)}
                  data-testid={`details-${row.id}`}
                >
                  {openId === row.id ? "إخفاء التفاصيل" : "التفاصيل"}
                </Button>
              </div>

              {openId === row.id && detail.isSuccess && (
                <div
                  className="mt-3 space-y-2 rounded-lg bg-slate-50 p-3 text-sm"
                  data-testid={`detail-${row.id}`}
                >
                  <p>
                    عند الإصدار:{" "}
                    <span className="font-bold">{detail.data.metric_value_at_issue}</span>{" "}
                    {WARNING_TYPE_UNITS[row.warning_type]} · حاليًا:{" "}
                    <span className="font-bold">{detail.data.current_metric_value}</span>{" "}
                    {WARNING_TYPE_UNITS[row.warning_type]}
                  </p>
                  {detail.data.metric_drifted && (
                    <p className="text-amber-800" data-testid={`drift-${row.id}`}>
                      تغيّر تصنيف بعض الأيام بعد إصدار الإنذار — الإنذار يبقى كما صدر.
                    </p>
                  )}
                  <p className="text-slate-600">
                    الصف/الفصل وقت الإصدار: {row.grade_name} / {row.section_name} · العام:{" "}
                    {detail.data.academic_year}
                  </p>
                  {row.notes && <p className="text-slate-600">ملاحظات: {row.notes}</p>}
                  {row.status === "VOIDED" && (
                    <p className="text-slate-600">
                      ألغي{row.voided_by && ` بواسطة ${row.voided_by}`}
                      {row.void_reason && ` — ${row.void_reason}`}
                    </p>
                  )}
                  {canVoid && row.status === "ISSUED" && (
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        value={voidReason}
                        onChange={(e) => setVoidReason(e.target.value)}
                        placeholder="سبب الإلغاء"
                        aria-label="سبب الإلغاء"
                        className="rounded-lg border border-slate-300 px-2 py-1 text-sm"
                        data-testid={`void-reason-${row.id}`}
                      />
                      <Button
                        variant="danger"
                        disabled={!voidReason.trim()}
                        onClick={() => {
                          setError(null);
                          void voidWarning(row.id, voidReason.trim())
                            .then(() => {
                              setVoidReason("");
                              return queryClient.invalidateQueries({
                                predicate: (q) =>
                                  JSON.stringify(q.queryKey).includes('"warnings"'),
                              });
                            })
                            .catch(setError);
                        }}
                        data-testid={`void-${row.id}`}
                      >
                        إلغاء الإنذار
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

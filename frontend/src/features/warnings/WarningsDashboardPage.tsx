import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, CalendarDays, FileText, Filter, LoaderCircle, Printer, RotateCcw, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { MetricCard } from "@/components/MetricCard";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import {
  documentPrintUrl,
  generateDocument,
  retryDocument,
  WARNING_LEVEL_DOCUMENT,
  type DocumentRow,
} from "@/features/documents/api";
import type {
  EligibilityRow,
  WarningLevel,
  WarningRow,
  WarningType,
} from "@/features/warnings/api";
import { roleLabel } from "@/utils/roles";
import {
  LEVEL_LABELS,
  WARNING_TYPE_LABELS,
  WARNING_TYPE_UNITS,
  getEligibility,
  issueWarning,
} from "@/features/warnings/api";

const TYPES: WarningType[] = ["UNEXCUSED_FULL_DAY_ABSENCE", "MORNING_LATE_OCCURRENCES"];
type IssuedWarning = EligibilityRow["issued_warnings"][number];

/** «يحتاج متابعة» — الاكتشاف تلقائي والإصدار قرار صريح من الوكيل/المدير. */
export function WarningsDashboardPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const schoolId = me.data?.active_school?.id ?? 0;
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const [type, setType] = useState<WarningType | "">("");
  const [grade, setGrade] = useState<number | "">("");
  const [status, setStatus] = useState<"due" | "issued" | "all">("due");
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState<string | null>(null);
  const [documentPending, setDocumentPending] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [issuedResult, setIssuedResult] = useState<{
    warning: WarningRow;
    document: DocumentRow | null;
  } | null>(null);

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

  const refreshWarnings = () =>
    queryClient.invalidateQueries({
      predicate: (q) => JSON.stringify(q.queryKey).includes('"warnings"'),
    });

  const issue = (row: EligibilityRow, level: WarningLevel) => {
    const key = `${row.student_id}-${row.warning_type}-${level}`;
    setPending(key);
    setError(null);
    setIssuedResult(null);
    void (async () => {
      try {
        const warning = await issueWarning({
          student_id: row.student_id,
          warning_type: row.warning_type,
          level,
        });
        setIssuedResult({ warning, document: null });

        // الإصدار الإداري وقالب الطباعة عمليتان مستقلتان؛ يبقى الإنذار صادرًا
        // حتى لو تعذر محرك PDF، وتظهر حينها إعادة التجهيز بوضوح.
        try {
          const document = await generateDocument({
            student_id: warning.student_id,
            document_type: WARNING_LEVEL_DOCUMENT[warning.level],
            warning_id: warning.id,
          });
          setIssuedResult({ warning, document });
        } catch (documentError) {
          setError(documentError);
        }
        await refreshWarnings();
      } catch (issueError) {
        setError(issueError);
      } finally {
        setPending(null);
      }
    })();
  };

  const prepareDocument = (studentId: number, warning: IssuedWarning) => {
    setDocumentPending(warning.id);
    setError(null);
    const request =
      warning.document?.status === "FAILED"
        ? retryDocument(warning.document.id)
        : generateDocument({
            student_id: studentId,
            document_type: WARNING_LEVEL_DOCUMENT[warning.level],
            warning_id: warning.id,
          });
    void request
      .then(async (document) => {
        if (issuedResult?.warning.id === warning.id) {
          setIssuedResult({ warning: issuedResult.warning, document });
        }
        await refreshWarnings();
      })
      .catch(setError)
      .finally(() => setDocumentPending(null));
  };

  if (eligibility.isPending) return <Spinner label="جارٍ حساب الاستحقاق..." />;
  if (eligibility.isError) return <ErrorState error={eligibility.error} />;
  const data = eligibility.data;
  if (!data) return null;

  return (
    <div className="space-y-5">
      <PageHeader
        icon={BellRing}
        eyebrow="الحوكمة والانضباط"
        title="الإنذارات المستحقة"
        description={`اكتشاف تلقائي ${schoolType === "GIRLS" ? "للطالبات اللاتي بلغن" : "للطلاب الذين بلغوا"} الحدود المعتمدة، مع إصدار رسمي ونسخة طباعة محفوظة لكل إنذار.`}
        tone="operational"
        badge={roleLabel(me.data?.roles.includes("SCHOOL_MANAGER") ? "SCHOOL_MANAGER" : "VICE_PRINCIPAL", me.data?.active_school?.school_type)}
        meta={<><CalendarDays aria-hidden size={14} /> العام الدراسي {data.academic_year.name}</>}
        testId="warnings-workspace-header"
      />

      <section className="grid grid-cols-1 gap-2 sm:grid-cols-2" data-testid="warning-kpis">
        {TYPES.map((current) => (
          <MetricCard
            key={current}
            testId={`kpi-${current}`}
            label={`${schoolType === "GIRLS" ? "بلغن" : "بلغوا"} حد ${WARNING_TYPE_LABELS[current]}`}
            value={data.summary[current]?.due_students ?? 0}
            hint={`صدرت لهم إنذارات: ${data.summary[current]?.issued_students ?? 0}`}
            icon={current === "UNEXCUSED_FULL_DAY_ABSENCE" ? ShieldAlert : BellRing}
            tone={current === "UNEXCUSED_FULL_DAY_ABSENCE" ? "red" : "amber"}
          />
        ))}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center gap-2"><Filter aria-hidden size={18} className="text-slate-500" /><h2 className="font-black text-slate-900">تصفية الاستحقاق</h2></div>
        <div className="flex flex-wrap items-center gap-3">
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
        </div>
      </section>

      {error != null && <ErrorState error={error} />}
      {issuedResult && (
        <section
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-950 shadow-sm"
          data-testid="issue-result"
          role="status"
        >
          <div className="flex items-start gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-emerald-100 text-emerald-700">
              <FileText aria-hidden size={20} />
            </span>
            <div>
              <p className="font-bold">
                صدر {issuedResult.warning.level_label} {schoolType === "GIRLS" ? "للطالبة" : "للطالب"} {issuedResult.warning.student_name}
              </p>
              <p className="mt-0.5 text-xs text-emerald-800">
                عند {issuedResult.warning.metric_value_at_issue} — النسخة الرسمية محفوظة من بيانات لحظة الإصدار.
              </p>
            </div>
          </div>
          {issuedResult.document?.status === "READY" && (
            <a
              href={documentPrintUrl(issuedResult.document.id)}
              target="_blank"
              rel="noreferrer"
              data-testid="issued-warning-print"
              className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-emerald-700 px-4 py-2.5 font-bold text-white shadow-sm transition hover:bg-emerald-800"
            >
              <Printer aria-hidden size={18} /> عرض وطباعة الإنذار
            </a>
          )}
          {issuedResult.document === null && pending && (
            <span className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-emerald-200 bg-white px-4 py-2.5 font-bold text-emerald-800">
              <LoaderCircle aria-hidden size={17} className="animate-spin" /> جارٍ تجهيز نسخة الطباعة…
            </span>
          )}
          {issuedResult.document === null && !pending && (
            <Button
              variant="secondary"
              onClick={() =>
                prepareDocument(issuedResult.warning.student_id, {
                  id: issuedResult.warning.id,
                  level: issuedResult.warning.level,
                  document: null,
                })
              }
              disabled={documentPending === issuedResult.warning.id}
            >
              <RotateCcw aria-hidden size={17} /> إعادة تجهيز نسخة الطباعة
            </Button>
          )}
          {issuedResult.document?.status === "FAILED" && (
            <Button
              variant="secondary"
              onClick={() =>
                prepareDocument(issuedResult.warning.student_id, {
                  id: issuedResult.warning.id,
                  level: issuedResult.warning.level,
                  document: { id: issuedResult.document!.id, status: "FAILED" },
                })
              }
              disabled={documentPending === issuedResult.warning.id}
            >
              <RotateCcw aria-hidden size={17} /> إعادة تجهيز نسخة الطباعة
            </Button>
          )}
        </section>
      )}

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        {data.results.length === 0 ? (
          <div className="p-4"><EmptyState title="لا توجد إنذارات ضمن هذا الفلتر" description="هذا مؤشر جيد. يمكنك تغيير النوع أو الحالة لمراجعة السجل الكامل." testId="no-due-students" compact /></div>
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
                    {(row.issued_warnings ?? []).map((warning) => {
                      const document = warning.document;
                      const isPreparing = documentPending === warning.id;
                      return (
                        <div
                          key={warning.id}
                          className="flex flex-wrap items-center gap-2 rounded-xl border border-sky-100 bg-sky-50 px-3 py-2"
                          data-testid={`warning-print-${warning.id}`}
                        >
                          <span className="text-xs font-bold text-sky-950">
                            {LEVEL_LABELS[warning.level]}
                          </span>
                          {document?.status === "READY" ? (
                            <a
                              href={documentPrintUrl(document.id)}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1.5 text-xs font-bold text-sky-800 underline decoration-sky-300 underline-offset-4"
                              data-testid={`print-warning-${warning.id}`}
                            >
                              <Printer aria-hidden size={15} /> عرض وطباعة
                            </a>
                          ) : document?.status === "PENDING" || isPreparing ? (
                            <span className="inline-flex items-center gap-1.5 text-xs text-sky-700">
                              <LoaderCircle aria-hidden size={14} className="animate-spin" /> جارٍ تجهيز النسخة…
                            </span>
                          ) : (
                            <button
                              type="button"
                              onClick={() => prepareDocument(row.student_id, warning)}
                              className="inline-flex items-center gap-1.5 text-xs font-bold text-sky-800 underline decoration-sky-300 underline-offset-4"
                              data-testid={`prepare-warning-${warning.id}`}
                            >
                              {document?.status === "FAILED" ? (
                                <RotateCcw aria-hidden size={15} />
                              ) : (
                                <FileText aria-hidden size={15} />
                              )}
                              {document?.status === "FAILED" ? "إعادة تجهيز النسخة" : "تجهيز نسخة الطباعة"}
                            </button>
                          )}
                        </div>
                      );
                    })}
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

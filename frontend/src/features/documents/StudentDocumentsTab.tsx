import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import {
  DOCUMENT_TYPE_LABELS,
  type DocumentPreview,
  type DocumentType,
  RANGE_DOCUMENT_TYPES,
  WARNING_LEVEL_DOCUMENT,
  documentDownloadUrl,
  generateDocument,
  getStudentDocuments,
  previewDocument,
  retryDocument,
  voidDocument,
} from "@/features/documents/api";
import { getStudentWarnings } from "@/features/warnings/api";
import { localIsoDate } from "@/utils/dates";
import { studentLabel } from "@/utils/roles";

const CREATABLE: DocumentType[] = [
  "ATTENDANCE_COMMITMENT",
  "ABSENCE_DETAIL_REPORT",
  "MORNING_LATE_DETAIL_REPORT",
  "STUDENT_ATTENDANCE_REPORT",
];

function summaryLine(preview: DocumentPreview): string {
  const snapshot = preview.snapshot as {
    warning?: { metric_value_at_issue?: number; unit?: string; level_label?: string };
    metrics?: { unexcused_full_absence_days?: number };
    totals?: { occurrences?: number; full_absence_days?: number };
  };
  if (snapshot.warning) {
    return `${snapshot.warning.level_label ?? ""} — صدر عند ${snapshot.warning.metric_value_at_issue} ${snapshot.warning.unit ?? ""}`;
  }
  if (snapshot.metrics?.unexcused_full_absence_days !== undefined) {
    return `غياب بدون عذر: ${snapshot.metrics.unexcused_full_absence_days} يوم`;
  }
  if (snapshot.totals) {
    const totals = snapshot.totals;
    if (totals.occurrences !== undefined) return `عدد السجلات: ${totals.occurrences}`;
    if (totals.full_absence_days !== undefined) {
      return `أيام الغياب الكامل: ${totals.full_absence_days}`;
    }
  }
  return "بيانات المستند جاهزة للمراجعة.";
}

/** تبويب المستندات في ملف الطالب — إنشاء بمعاينة، وعرض/إعادة طباعة النسخة المخزنة. */
export function StudentDocumentsTab({ studentId }: { studentId: number }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const schoolId = me.data?.active_school?.id ?? 0;
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const documentTypeLabel = (type: DocumentType) => type === "STUDENT_ATTENDANCE_REPORT"
    ? `تقرير مواظبة ${studentLabel(schoolType, true)}`
    : DOCUMENT_TYPE_LABELS[type];
  const canManage =
    me.data?.roles.some((role) => role === "SCHOOL_MANAGER" || role === "VICE_PRINCIPAL") ?? false;
  const canVoid = me.data?.roles.includes("SCHOOL_MANAGER") ?? false;

  const today = localIsoDate();
  const [documentType, setDocumentType] = useState<DocumentType>("ATTENDANCE_COMMITMENT");
  const [warningId, setWarningId] = useState<string>("");
  const [fromDate, setFromDate] = useState(today);
  const [toDate, setToDate] = useState(today);
  const [previewState, setPreviewState] = useState<{
    data: DocumentPreview;
    key: string;
    payload: ReturnType<typeof buildPayload>;
  } | null>(null);
  const [voidId, setVoidId] = useState<number | null>(null);
  const [voidReason, setVoidReason] = useState("");
  const [error, setError] = useState<unknown>(null);

  const list = useQuery({
    queryKey: schoolScopedKey(schoolId, "documents", studentId),
    queryFn: ({ signal }) => getStudentDocuments(studentId, signal),
    enabled: schoolId > 0,
  });
  const warnings = useQuery({
    queryKey: schoolScopedKey(schoolId, "warnings", "student", studentId),
    queryFn: ({ signal }) => getStudentWarnings(studentId, signal),
    enabled: schoolId > 0 && canManage,
  });

  const refresh = () =>
    queryClient.invalidateQueries({
      queryKey: schoolScopedKey(schoolId, "documents", studentId),
    });

  const isWarningDocument = documentType.startsWith("WARNING_LEVEL_");
  const needsRange = RANGE_DOCUMENT_TYPES.includes(documentType);
  function buildPayload() {
    return {
      student_id: studentId,
      document_type: documentType,
      ...(isWarningDocument && warningId ? { warning_id: Number(warningId) } : {}),
      ...(needsRange ? { from_date: fromDate, to_date: toDate } : {}),
    };
  }
  const currentPayload = buildPayload();
  const currentPreviewKey = JSON.stringify(currentPayload);
  const preview = previewState?.key === currentPreviewKey ? previewState.data : null;

  const runPreview = useMutation({
    mutationFn: (requestPayload: ReturnType<typeof buildPayload>) => previewDocument(requestPayload),
    onSuccess: (data, requestPayload) => {
      setPreviewState({ data, key: JSON.stringify(requestPayload), payload: requestPayload });
      setError(null);
    },
    onError: (err) => {
      setPreviewState(null);
      setError(err);
    },
  });

  const create = useMutation({
    mutationFn: (requestPayload: ReturnType<typeof buildPayload>) =>
      generateDocument({
        ...requestPayload,
        create_action: requestPayload.document_type === "ATTENDANCE_COMMITMENT",
      }),
    onSuccess: async () => {
      setPreviewState(null);
      setError(null);
      await refresh();
    },
    onError: setError,
  });

  const retry = useMutation({
    mutationFn: (id: number) => retryDocument(id),
    onSuccess: async () => {
      setError(null);
      await refresh();
    },
    onError: setError,
  });

  const voidIt = useMutation({
    mutationFn: (id: number) => voidDocument(id, voidReason),
    onSuccess: async () => {
      setVoidId(null);
      setVoidReason("");
      setError(null);
      await refresh();
    },
    onError: setError,
  });

  if (list.isPending) return <Spinner />;
  if (list.isError) return <ErrorState error={list.error} />;

  const rows = list.data?.results ?? [];
  const issuedWarnings = (warnings.data?.results ?? []).filter((row) => row.status === "ISSUED");
  const warningTypes = issuedWarnings.map((warning) => ({
    id: warning.id,
    label: `${warning.level_label} — ${warning.warning_type_label}`,
    documentType: WARNING_LEVEL_DOCUMENT[warning.level],
  }));

  return (
    <div className="space-y-5 text-slate-800" data-testid="student-documents-tab">
      {error != null && <ErrorState error={error} />}

      {canManage && (
        <div
          className="overflow-hidden rounded-2xl border border-teal-200 bg-[#fbfdfb] shadow-sm"
          data-testid="document-form"
        >
          <div className="border-b border-teal-100 bg-[#edf6f2] px-5 py-4">
            <p className="text-xs font-bold tracking-wide text-teal-800">مستندات الطالب</p>
            <h2 className="mt-1 text-lg font-bold text-slate-950">إنشاء مستند مدرسي</h2>
            <p className="mt-1 text-sm leading-6 text-slate-600">راجع البيانات المثبتة قبل الإصدار. لا يُنشأ المستند إلا بعد المعاينة.</p>
          </div>
          <div className="space-y-4 p-5">
            <label htmlFor="document-type-select" className="flex max-w-2xl flex-col gap-1.5 text-sm font-semibold text-slate-800">
              نوع المستند
              <select
                id="document-type-select"
                data-testid="document-type"
                value={documentType}
                onChange={(event) => {
                  setDocumentType(event.target.value as DocumentType);
                  setWarningId("");
                  setPreviewState(null);
                }}
                className="min-h-11 rounded-xl border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm outline-none transition focus:border-teal-700 focus:ring-2 focus:ring-teal-700/15"
              >
                {CREATABLE.map((type) => (
                  <option key={type} value={type}>
                    {documentTypeLabel(type)}
                  </option>
                ))}
                {warningTypes.map((warning) => (
                  <option key={warning.id} value={warning.documentType}>
                    {documentTypeLabel(warning.documentType)}
                  </option>
                ))}
              </select>
            </label>

          {isWarningDocument && (
            <label htmlFor="document-warning-select" className="flex max-w-2xl flex-col gap-1.5 text-sm font-semibold text-slate-800">
              الإنذار
              <select
                id="document-warning-select"
                data-testid="document-warning"
                value={warningId}
                onChange={(event) => {
                  setWarningId(event.target.value);
                  setPreviewState(null);
                }}
                className="min-h-11 rounded-xl border border-slate-300 bg-white px-3 py-2 outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-700/15"
              >
                <option value="">اختر الإنذار</option>
                {warningTypes
                  .filter((warning) => warning.documentType === documentType)
                  .map((warning) => (
                    <option key={warning.id} value={warning.id}>
                      {warning.label}
                    </option>
                  ))}
              </select>
              {warningTypes.filter((warning) => warning.documentType === documentType).length === 0 && (
                <span className="text-xs font-normal text-amber-800">لا يوجد إنذار صادر من هذا المستوى لهذا الطالب.</span>
              )}
            </label>
          )}

          {needsRange && (
            <div className="grid max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2">
              <label htmlFor="document-from-date" className="flex flex-col gap-1.5 text-sm font-semibold">
                من
                <input
                  id="document-from-date"
                  type="date"
                  data-testid="document-from"
                  value={fromDate}
                  onChange={(event) => { setFromDate(event.target.value); setPreviewState(null); }}
                  className="min-h-11 rounded-xl border border-slate-300 bg-white px-3 py-2 outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-700/15"
                />
              </label>
              <label htmlFor="document-to-date" className="flex flex-col gap-1.5 text-sm font-semibold">
                إلى
                <input
                  id="document-to-date"
                  type="date"
                  data-testid="document-to"
                  value={toDate}
                  onChange={(event) => { setToDate(event.target.value); setPreviewState(null); }}
                  className="min-h-11 rounded-xl border border-slate-300 bg-white px-3 py-2 outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-700/15"
                />
              </label>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-4">
            <Button
              data-testid="preview-document"
              onClick={() => runPreview.mutate(currentPayload)}
              disabled={runPreview.isPending || create.isPending || (isWarningDocument && !warningId) || (needsRange && (!fromDate || !toDate || fromDate > toDate))}
            >
              {runPreview.isPending ? "جارٍ تجهيز المعاينة…" : "معاينة البيانات"}
            </Button>
            {runPreview.isPending && <span role="status" className="text-sm text-slate-600">نحدّث تفاصيل المستند المحدد…</span>}
            {preview && (
              <Button
                data-testid="create-document"
                onClick={() => {
                  if (previewState && previewState.key === currentPreviewKey && !previewState.data.already_exists) {
                    create.mutate(previewState.payload);
                  }
                }}
                disabled={create.isPending || preview.already_exists}
              >
                {create.isPending ? "جارٍ الإنشاء…" : "إنشاء المستند"}
              </Button>
            )}
          </div>
          {needsRange && fromDate && toDate && fromDate > toDate && (
            <p role="alert" className="text-sm font-medium text-rose-800">تاريخ البداية يجب أن يسبق تاريخ النهاية أو يساويه.</p>
          )}

          {preview && (
            <div
              className={`rounded-xl border p-4 text-sm ${preview.already_exists ? "border-amber-300 bg-amber-50" : "border-teal-200 bg-white"}`}
              data-testid="document-preview"
            >
              <p className="font-bold text-slate-950">{preview.document_type_label}</p>
              <p className="mt-1 text-slate-700">{summaryLine(preview)}</p>
              <p className="mt-2 text-xs text-slate-600">إصدار القالب: <span dir="ltr" className="font-mono">{preview.template}</span></p>
              {preview.already_exists && (
                <p role="status" className="mt-2 font-semibold text-amber-900">
                  يوجد مستند أصلي لهذا الإنذار — الإنشاء مرة أخرى مرفوض حتى يُلغى الأصلي.
                </p>
              )}
            </div>
          )}
          </div>
        </div>
      )}

      {rows.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-teal-300 bg-[#f6faf8] px-5 py-8 text-center">
          <p className="font-bold text-slate-800">لا توجد مستندات محفوظة بعد</p>
          <p className="mt-1 text-sm text-slate-600">لا توجد مستندات {schoolType === "GIRLS" ? "لهذه الطالبة" : "لهذا الطالب"}. ستظهر النسخ الصادرة هنا.</p>
        </div>
      ) : (
        <ul className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          {rows.map((row) => (
            <li key={row.id} className="space-y-3 p-4 sm:p-5" data-testid={`doc-row-${row.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <span className="font-bold text-slate-950">{row.document_type_label}</span>
                  <span className={`ms-2 inline-flex rounded-full px-2.5 py-1 text-xs font-bold ${row.status === "READY" ? "bg-teal-50 text-teal-800" : row.status === "FAILED" ? "bg-rose-50 text-rose-800" : row.status === "VOIDED" ? "bg-slate-100 text-slate-600" : "bg-amber-50 text-amber-800"}`} data-testid={`doc-status-${row.id}`}>{row.status_label}</span>
                </div>
                <span className="text-sm text-slate-600">
                  {(row.generated_at ?? "").slice(0, 10)} <span aria-hidden="true">·</span> {row.generated_by_name ?? "—"}
                </span>
              </div>
              <p className="text-sm text-slate-600">
                النسخة: <span dir="ltr" className="font-mono text-xs">{row.template}</span>
                {row.error_code && <span className="ms-2 text-rose-800">({row.error_code})</span>}
              </p>

              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-100 pt-3">
                {row.can_download && (
                  <a
                    data-testid={`doc-download-${row.id}`}
                    href={documentDownloadUrl(row.id)}
                    className="rounded font-semibold text-teal-800 underline decoration-teal-300 underline-offset-4 hover:text-teal-950 focus:outline-none focus:ring-2 focus:ring-teal-700"
                  >
                    عرض / إعادة طباعة
                  </a>
                )}
                {canManage && row.status === "FAILED" && (
                  <button
                    type="button"
                    data-testid={`doc-retry-${row.id}`}
                    onClick={() => retry.mutate(row.id)}
                    className="rounded font-semibold text-teal-800 underline decoration-teal-300 underline-offset-4 focus:outline-none focus:ring-2 focus:ring-teal-700"
                  >
                    إعادة المحاولة
                  </button>
                )}
                {canVoid && row.status !== "VOIDED" && (
                  <>
                    {voidId === row.id ? (
                      <span className="flex flex-wrap items-center gap-2">
                        <input
                          data-testid="void-document-reason"
                          value={voidReason}
                          onChange={(event) => setVoidReason(event.target.value)}
                          aria-label="سبب إلغاء المستند"
                          placeholder="سبب الإلغاء"
                          className="min-h-10 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-rose-700 focus:ring-2 focus:ring-rose-700/15"
                        />
                        <Button
                          data-testid="confirm-void-document"
                          onClick={() => voidIt.mutate(row.id)}
                          disabled={voidReason.trim().length === 0 || voidIt.isPending}
                        >
                          تأكيد الإلغاء
                        </Button>
                      </span>
                    ) : (
                      <button
                        type="button"
                        data-testid={`doc-void-${row.id}`}
                        onClick={() => setVoidId(row.id)}
                        className="rounded text-sm font-semibold text-rose-800 underline decoration-rose-300 underline-offset-4 focus:outline-none focus:ring-2 focus:ring-rose-700"
                      >
                        إلغاء المستند
                      </button>
                    )}
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

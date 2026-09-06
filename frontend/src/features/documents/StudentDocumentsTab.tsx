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
  "PERIOD_LATE_DETAIL_REPORT",
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
  const [preview, setPreview] = useState<DocumentPreview | null>(null);
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
  const payload = () => ({
    student_id: studentId,
    document_type: documentType,
    ...(isWarningDocument && warningId ? { warning_id: Number(warningId) } : {}),
    ...(needsRange ? { from_date: fromDate, to_date: toDate } : {}),
  });

  const runPreview = useMutation({
    mutationFn: () => previewDocument(payload()),
    onSuccess: (data) => {
      setPreview(data);
      setError(null);
    },
    onError: (err) => {
      setPreview(null);
      setError(err);
    },
  });

  const create = useMutation({
    mutationFn: () =>
      generateDocument({
        ...payload(),
        create_action: documentType === "ATTENDANCE_COMMITMENT",
      }),
    onSuccess: async () => {
      setPreview(null);
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
    <div className="space-y-3" data-testid="student-documents-tab">
      {error != null && <ErrorState error={error} />}

      {canManage && (
        <div
          className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
          data-testid="document-form"
        >
          <label className="flex flex-col gap-1 text-sm">
            نوع المستند
            <select
              data-testid="document-type"
              value={documentType}
              onChange={(event) => {
                setDocumentType(event.target.value as DocumentType);
                setPreview(null);
              }}
              className="rounded-lg border border-slate-300 px-3 py-2"
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
            <label className="flex flex-col gap-1 text-sm">
              الإنذار
              <select
                data-testid="document-warning"
                value={warningId}
                onChange={(event) => {
                  setWarningId(event.target.value);
                  setPreview(null);
                }}
                className="rounded-lg border border-slate-300 px-3 py-2"
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
            </label>
          )}

          {needsRange && (
            <div className="flex flex-wrap gap-3">
              <label className="flex flex-col gap-1 text-sm">
                من
                <input
                  type="date"
                  data-testid="document-from"
                  value={fromDate}
                  onChange={(event) => setFromDate(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                إلى
                <input
                  type="date"
                  data-testid="document-to"
                  value={toDate}
                  onChange={(event) => setToDate(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button
              data-testid="preview-document"
              onClick={() => runPreview.mutate()}
              disabled={runPreview.isPending || (isWarningDocument && !warningId)}
            >
              معاينة البيانات
            </Button>
            {preview && (
              <Button
                data-testid="create-document"
                onClick={() => create.mutate()}
                disabled={create.isPending}
              >
                {create.isPending ? "جارٍ الإنشاء…" : "إنشاء المستند"}
              </Button>
            )}
          </div>

          {preview && (
            <div
              className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm"
              data-testid="document-preview"
            >
              <p className="font-semibold">{preview.document_type_label}</p>
              <p>{summaryLine(preview)}</p>
              <p className="text-slate-600">القالب: {preview.template}</p>
              {preview.already_exists && (
                <p className="text-amber-700">
                  يوجد مستند أصلي لهذا الإنذار — الإنشاء مرة أخرى مرفوض حتى يُلغى الأصلي.
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {rows.length === 0 ? (
        <p className="rounded-xl border border-slate-200 bg-white p-6 text-slate-600 shadow-sm">
          لا توجد مستندات {schoolType === "GIRLS" ? "لهذه الطالبة" : "لهذا الطالب"}.
        </p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white shadow-sm">
          {rows.map((row) => (
            <li key={row.id} className="space-y-1 p-4" data-testid={`doc-row-${row.id}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold">{row.document_type_label}</span>
                <span className="text-sm text-slate-600">
                  {(row.generated_at ?? "").slice(0, 10)} · {row.generated_by_name ?? "—"}
                </span>
              </div>
              <p className="text-sm text-slate-600">
                النسخة: {row.template} · الحالة:{" "}
                <span data-testid={`doc-status-${row.id}`}>{row.status_label}</span>
                {row.error_code && ` (${row.error_code})`}
              </p>

              <div className="flex flex-wrap items-center gap-3 pt-1">
                {row.can_download && (
                  <a
                    data-testid={`doc-download-${row.id}`}
                    href={documentDownloadUrl(row.id)}
                    className="text-sm text-blue-700 underline"
                  >
                    عرض / إعادة طباعة
                  </a>
                )}
                {canManage && row.status === "FAILED" && (
                  <button
                    type="button"
                    data-testid={`doc-retry-${row.id}`}
                    onClick={() => retry.mutate(row.id)}
                    className="text-sm text-blue-700 underline"
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
                          placeholder="سبب الإلغاء"
                          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
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
                        className="text-sm text-red-700 underline"
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

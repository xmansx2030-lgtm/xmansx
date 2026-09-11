import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey } from "@/features/auth/useMe";
import {
  type ExcusePreview,
  approveExcuse,
  attachmentDownloadUrl,
  cancelExcuse,
  getExcuse,
  previewExcuse,
  rejectExcuse,
  uploadExcuseAttachment,
} from "@/features/excuses/api";
import { StatusBadge, formatDate } from "@/features/excuses/ExcusesPage";
import { useActiveSchoolId } from "@/features/settings/hooks";

/** تفاصيل العذر: النطاق، التغطية الفعلية، المرفقات، وإجراءات دورة الحياة. */
export function ExcuseDetailCard({
  excuseId,
  canManage,
  onChanged,
  onClose,
}: {
  excuseId: number;
  canManage: boolean;
  onChanged: () => void;
  onClose: () => void;
}) {
  const schoolId = useActiveSchoolId();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<ExcusePreview | null>(null);
  const [reason, setReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const detail = useQuery({
    queryKey: schoolScopedKey(schoolId, "excuse-detail", excuseId),
    queryFn: ({ signal }) => getExcuse(excuseId, signal),
    enabled: schoolId > 0,
  });

  const refreshAll = () => {
    queryClient.invalidateQueries({
      queryKey: schoolScopedKey(schoolId, "excuse-detail", excuseId),
    });
    onChanged();
  };

  const previewMutation = useMutation({
    mutationFn: () => previewExcuse(excuseId),
    onSuccess: (data) => {
      setPreview(data);
      setActionError(null);
    },
    onError: (error: { message?: string }) =>
      setActionError(error.message ?? "تعذر إجراء المعاينة."),
  });

  const approveMutation = useMutation({
    mutationFn: () => approveExcuse(excuseId, preview!.preview_hash),
    onSuccess: () => {
      setPreview(null);
      refreshAll();
    },
    onError: (error: { message?: string }) =>
      setActionError(error.message ?? "تعذر اعتماد العذر."),
  });

  const rejectMutation = useMutation({
    mutationFn: () => rejectExcuse(excuseId, reason),
    onSuccess: refreshAll,
    onError: (error: { message?: string }) =>
      setActionError(error.message ?? "تعذر رفض العذر."),
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelExcuse(excuseId, reason),
    onSuccess: refreshAll,
    onError: (error: { message?: string }) =>
      setActionError(error.message ?? "تعذر إلغاء العذر."),
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadExcuseAttachment(excuseId, file),
    onSuccess: refreshAll,
    onError: (error: { message?: string }) =>
      setActionError(error.message ?? "تعذر رفع المرفق."),
  });

  if (detail.isPending) return <Spinner />;
  if (detail.isError) return <ErrorState error={detail.error} />;
  const excuse = detail.data;
  const activeCoverages = excuse.coverages.filter((c) => c.status === "ACTIVE");

  return (
    <div
      className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
      data-testid="excuse-detail"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold">{excuse.student.full_name}</h2>
          <p className="text-sm text-slate-600">
            {excuse.reason_type_label}
            <span className="mx-2">•</span>
            <StatusBadge status={excuse.status} label={excuse.status_label} />
          </p>
        </div>
        <Button variant="secondary" onClick={onClose}>
          إغلاق
        </Button>
      </div>

      {excuse.notes && <p className="text-sm text-slate-700">الملاحظات: {excuse.notes}</p>}

      <section>
        <h3 className="mb-2 text-sm font-bold">نطاق العذر</h3>
        <ul className="divide-y rounded-lg border border-slate-200 text-sm">
          {excuse.targets.map((target) => (
            <li key={target.id} className="flex justify-between p-2">
              <span>{formatDate(target.attendance_date)}</span>
              <span className="text-slate-600">
                {target.period_sequence === null
                  ? "يوم كامل"
                  : `الحصة ${target.period_sequence}`}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="mb-2 text-sm font-bold">
          الحصص المغطاة فعليًا: {activeCoverages.length}
        </h3>
        {excuse.coverages.length === 0 ? (
          <p className="text-sm text-slate-500" data-testid="no-coverage">
            لا توجد تغطية بعد — الاعتماد ينشئها.
          </p>
        ) : (
          <ul className="divide-y rounded-lg border border-slate-200 text-sm">
            {excuse.coverages.map((coverage) => (
              <li
                key={coverage.id}
                className="flex justify-between p-2"
                data-testid={`coverage-${coverage.id}`}
              >
                <span>
                  {formatDate(coverage.attendance_date)} — الحصة{" "}
                  {coverage.period_sequence}
                </span>
                <span
                  className={
                    coverage.status === "ACTIVE" ? "text-emerald-700" : "text-slate-400"
                  }
                >
                  {coverage.status_label}
                  {coverage.void_reason === "ATTENDANCE_CHANGED" && " (تغير الحضور)"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-bold">المرفقات</h3>
        <ul className="divide-y rounded-lg border border-slate-200 text-sm">
          {excuse.attachments.map((attachment) => (
            <li key={attachment.id} className="flex justify-between p-2">
              <a
                href={attachmentDownloadUrl(excuse.id, attachment.id)}
                target="_blank"
                rel="noreferrer"
                className="text-blue-700 underline"
                data-testid={`attachment-${attachment.id}`}
              >
                {attachment.original_filename}
              </a>
              <span className="text-slate-500">
                {Math.round(attachment.size_bytes / 1024)} ك.ب
              </span>
            </li>
          ))}
          {excuse.attachments.length === 0 && (
            <li className="p-2 text-slate-500">لا توجد مرفقات.</li>
          )}
        </ul>
        {canManage && (excuse.status === "PENDING" || excuse.status === "APPROVED") && (
          <div className="mt-2">
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png"
              className="hidden"
              data-testid="attachment-input"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) uploadMutation.mutate(file);
                event.target.value = "";
              }}
            />
            <Button
              variant="secondary"
              onClick={() => fileInput.current?.click()}
              disabled={uploadMutation.isPending}
            >
              {uploadMutation.isPending ? "جارٍ الرفع..." : "إرفاق ملف (PDF/JPG/PNG)"}
            </Button>
          </div>
        )}
      </section>

      {preview && (
        <section
          className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm"
          data-testid="excuse-preview"
        >
          <h3 className="mb-2 font-bold">
            المعاينة: {preview.covered_absent_periods} حصة غياب سيتحول تصنيفها إلى «بعذر»
          </h3>
          <ul className="space-y-1">
            {preview.days.map((day) => (
              <li key={day.attendance_date} data-testid={`preview-day-${day.attendance_date}`}>
                <strong>{formatDate(day.attendance_date)}:</strong> إجمالي الغياب المسجل {day.absent_periods}، والنطاق المشمول {day.scope_periods} حصة
                {day.present_periods > 0 && ` • ${day.present_periods} حاضر (لن تتأثر)`}
                {!day.complete && (
                  <span className="text-amber-800">
                    {" "}
                    • بيانات اليوم غير مكتملة: {day.missing_periods} حصة لم تعتمد بعد
                  </span>
                )}
              </li>
            ))}
          </ul>
          {preview.already_excused_periods > 0 && (
            <p role="alert" className="mt-2 text-red-800">
              تحذير: {preview.already_excused_periods} حصة مغطاة مسبقًا بعذر معتمد آخر.
            </p>
          )}
          {canManage && (
            <Button
              className="mt-3"
              onClick={() => approveMutation.mutate()}
              disabled={approveMutation.isPending}
              data-testid="confirm-approve"
            >
              {approveMutation.isPending ? "جارٍ الاعتماد..." : "اعتماد العذر"}
            </Button>
          )}
        </section>
      )}

      {actionError && (
        <p role="alert" className="text-sm text-red-700" data-testid="excuse-action-error">
          {actionError}
        </p>
      )}

      {canManage && (
        <div className="flex flex-wrap items-end gap-2 border-t border-slate-100 pt-3">
          {excuse.status === "PENDING" && (
            <>
              <Button
                onClick={() => previewMutation.mutate()}
                disabled={previewMutation.isPending}
                data-testid="preview-excuse"
              >
                {previewMutation.isPending ? "جارٍ المعاينة..." : "معاينة الأثر"}
              </Button>
              <label className="flex flex-col gap-1 text-sm">
                سبب الرفض/الإلغاء
                <input
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  data-testid="decision-reason"
                  className="rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <Button
                variant="danger"
                onClick={() => rejectMutation.mutate()}
                disabled={reason.trim().length === 0 || rejectMutation.isPending}
                data-testid="reject-excuse"
              >
                رفض
              </Button>
            </>
          )}
          {excuse.status === "APPROVED" && (
            <>
              <label className="flex flex-col gap-1 text-sm">
                سبب الإلغاء
                <input
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  data-testid="decision-reason"
                  className="rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <Button
                variant="danger"
                onClick={() => cancelMutation.mutate()}
                disabled={reason.trim().length === 0 || cancelMutation.isPending}
                data-testid="cancel-excuse"
              >
                إلغاء الاعتماد
              </Button>
            </>
          )}
        </div>
      )}

      <p className="text-xs text-slate-500">
        سجل: تم التسجيل بواسطة {excuse.recorded_by_name ?? "—"}
        {excuse.approved_by_name && ` • اعتمده ${excuse.approved_by_name}`}
        {excuse.rejected_by_name && ` • رفضه ${excuse.rejected_by_name}`}
        {excuse.cancelled_by_name && ` • ألغاه ${excuse.cancelled_by_name}`}
        {excuse.rejection_reason && ` — السبب: ${excuse.rejection_reason}`}
        {excuse.cancellation_reason && ` — السبب: ${excuse.cancellation_reason}`}
      </p>
    </div>
  );
}

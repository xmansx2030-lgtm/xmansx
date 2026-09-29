import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { Modal } from "@/components/Modal";
import {
  applyStudentMerge,
  previewStudentMerge,
  type StudentMergePreview,
  type StudentRow,
} from "@/features/students/api";

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "تعذر إتمام العملية. حاول مرة أخرى.";
}

export function StudentMergeDialog({
  rows,
  studentLabel,
  onClose,
  onMerged,
}: {
  rows: StudentRow[];
  studentLabel: string;
  onClose: () => void;
  onMerged: (targetId: number, count: number) => void;
}) {
  const [targetId, setTargetId] = useState(rows[0]?.id ?? 0);
  const [preview, setPreview] = useState<StudentMergePreview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const previewMutation = useMutation({
    mutationFn: () => previewStudentMerge(targetId, rows.filter((row) => row.id !== targetId).map((row) => row.id)),
    onSuccess: (result) => {
      setPreview(result);
      setConfirmed(false);
    },
  });
  const mergeMutation = useMutation({
    mutationFn: (token: string) => applyStudentMerge(token),
    onSuccess: (result) => onMerged(result.target_id, result.archived_source_ids.length),
  });

  return (
    <Modal
      title="دمج سجلات الطالب"
      description={`راجع السجلات المحددة واختر الرقم الذي سيبقى ملف ${studentLabel} المعتمد. لن يتم أي تغيير قبل المعاينة والتأكيد.`}
      onClose={onClose}
    >
      <div className="space-y-5 text-sm">
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 leading-6 text-amber-950">
          تأكد من الهوية ورقم الطالب وسجل الحضور. تطابق الاسم وحده لا يثبت أن السجلات تخص الشخص نفسه.
        </div>
        <fieldset className="space-y-2">
          <legend className="mb-2 font-bold text-slate-900">السجل الذي سيبقى معتمدًا</legend>
          {rows.map((row) => (
            <label
              key={row.id}
              className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 ${targetId === row.id ? "border-teal-600 bg-teal-50" : "border-slate-200 bg-white"}`}
            >
              <input
                type="radio"
                name="merge-target"
                value={row.id}
                checked={targetId === row.id}
                onChange={() => {
                  setTargetId(row.id);
                  setPreview(null);
                  setConfirmed(false);
                  previewMutation.reset();
                  mergeMutation.reset();
                }}
                className="mt-1 size-4"
              />
              <span className="min-w-0">
                <strong className="block text-slate-900">{row.full_name}</strong>
                <span className="block text-slate-700">
                  رقم الطالب <span dir="ltr" className="inline-block font-semibold">{row.national_id_masked}</span>
                  {row.student_number ? ` · الرقم الأكاديمي ${row.student_number}` : ""}
                </span>
                <span className="block text-slate-600">{row.grade?.name ?? "بلا صف"} / {row.section?.name ?? "بلا فصل"}{row.section?.department ? ` / ${row.section.department}` : ""}</span>
              </span>
            </label>
          ))}
        </fieldset>

        <Button
          variant="secondary"
          fullWidth
          loading={previewMutation.isPending}
          loadingLabel="جارٍ فحص السجلات..."
          disabled={mergeMutation.isPending}
          onClick={() => previewMutation.mutate()}
        >
          معاينة أثر الدمج
        </Button>
        {previewMutation.isError && <p role="alert" className="text-red-700">{errorMessage(previewMutation.error)}</p>}

        {preview && (
          <section aria-label="نتيجة معاينة الدمج" className="space-y-4 border-t border-slate-200 pt-4">
            <h3 className="font-bold text-slate-900">ماذا سيحدث؟</h3>
            <p className="leading-6 text-slate-700">
              سيبقى الرقم <span dir="ltr" className="inline-block font-bold">{preview.students.find((row) => row.id === preview.target_id)?.national_id_masked ?? "—"}</span> نشطًا،
              وتُؤرشف {preview.summary.archived_records} من السجلات الأخرى مع ربطها به. سيُنقل تاريخ الحضور والقيود القابلة للدمج.
            </p>
            <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {[
                ["أيام حضور محفوظة", preview.summary.attendance_days],
                ["ملخصات مكررة ستُزال", preview.summary.duplicate_daily_summaries],
                ["علامات مكررة ستُزال", preview.summary.duplicate_attendance_marks],
                ["قيود تاريخية منقولة", preview.summary.historical_enrollments],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg bg-slate-50 p-3">
                  <dt className="text-slate-600">{label}</dt>
                  <dd className="mt-1 font-bold text-slate-900">{value}</dd>
                </div>
              ))}
            </dl>
            {preview.history_adjustments.length > 0 && (
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-3 text-blue-950">
                <strong>تاريخ الفصل الذي سيُحفظ</strong>
                <ul className="mt-2 list-inside list-disc space-y-1">
                  {preview.history_adjustments.map((item) => (
                    <li key={item.source_id}>
                      {item.grade} / {item.section}: من {item.from_date} إلى {item.through_date}؛ يبدأ الفصل المعتمد في {item.current_from_date}.
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {preview.warnings.length > 0 && (
              <ul className="space-y-1 rounded-xl border border-amber-200 bg-amber-50 p-3 text-amber-950">
                {preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}
              </ul>
            )}
            {preview.blockers.length > 0 && (
              <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-red-900">
                <strong>يتعذر الدمج الآن</strong>
                <ul className="mt-2 list-inside list-disc space-y-1">
                  {preview.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
                </ul>
              </div>
            )}
            {preview.can_merge && preview.confirmation_token && (
              <>
                <label className="flex items-start gap-2 rounded-xl border border-slate-200 p-3 leading-6">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(event) => setConfirmed(event.target.checked)}
                    className="mt-1 size-4"
                  />
                  <span>راجعت الأرقام والحضور وأؤكد أن هذه السجلات تخص {studentLabel} نفسه، وأن الرقم المختار هو المعتمد.</span>
                </label>
                <Button
                  fullWidth
                  disabled={!confirmed}
                  loading={mergeMutation.isPending}
                  loadingLabel="جارٍ حفظ الدمج..."
                  onClick={() => mergeMutation.mutate(preview.confirmation_token!)}
                >
                  تأكيد الدمج وحفظ التاريخ
                </Button>
              </>
            )}
            {mergeMutation.isError && <p role="alert" className="text-red-700">{errorMessage(mergeMutation.error)} أعد المعاينة إذا تغيرت البيانات.</p>}
          </section>
        )}
      </div>
    </Modal>
  );
}

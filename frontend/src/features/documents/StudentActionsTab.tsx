import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import {
  ACTION_TYPE_LABELS,
  ACTION_TYPES,
  type ActionType,
  cancelStudentAction,
  createStudentAction,
  getStudentActions,
} from "@/features/documents/api";
import { LEVEL_LABELS, getStudentWarnings } from "@/features/warnings/api";
import { studentLabel } from "@/utils/roles";

/** تبويب الإجراءات في ملف الطالب — تسجيل ما فُعل (لا ما استحقه الطالب). */
export function StudentActionsTab({ studentId }: { studentId: number }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const schoolId = me.data?.active_school?.id ?? 0;
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const actionTypeLabel = (type: ActionType) => type === "STUDENT_MEETING"
    ? `مقابلة ${studentLabel(schoolType, true)}`
    : ACTION_TYPE_LABELS[type];
  const canManage =
    me.data?.roles.some((role) => role === "SCHOOL_MANAGER" || role === "VICE_PRINCIPAL") ?? false;

  const [open, setOpen] = useState(false);
  const [actionType, setActionType] = useState<ActionType>("PARENT_CONTACT");
  const [warningId, setWarningId] = useState<string>("");
  const [notes, setNotes] = useState("");
  const [cancelId, setCancelId] = useState<number | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [error, setError] = useState<unknown>(null);

  const list = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-actions", studentId),
    queryFn: ({ signal }) => getStudentActions(studentId, signal),
    enabled: schoolId > 0,
  });
  const warnings = useQuery({
    queryKey: schoolScopedKey(schoolId, "warnings", "student", studentId),
    queryFn: ({ signal }) => getStudentWarnings(studentId, signal),
    enabled: schoolId > 0 && canManage,
  });

  const refresh = () =>
    queryClient.invalidateQueries({
      queryKey: schoolScopedKey(schoolId, "student-actions", studentId),
    });

  const create = useMutation({
    mutationFn: () =>
      createStudentAction({
        student_id: studentId,
        action_type: actionType,
        warning_id: warningId ? Number(warningId) : null,
        notes,
      }),
    onSuccess: async () => {
      setOpen(false);
      setNotes("");
      setWarningId("");
      setError(null);
      await refresh();
    },
    onError: setError,
  });

  const cancel = useMutation({
    mutationFn: (id: number) => cancelStudentAction(id, cancelReason),
    onSuccess: async () => {
      setCancelId(null);
      setCancelReason("");
      setError(null);
      await refresh();
    },
    onError: setError,
  });

  if (list.isPending) return <Spinner />;
  if (list.isError) return <ErrorState error={list.error} />;

  const rows = list.data?.results ?? [];
  const issuedWarnings = (warnings.data?.results ?? []).filter((row) => row.status === "ISSUED");

  return (
    <div className="space-y-3" data-testid="student-actions-tab">
      {error != null && <ErrorState error={error} />}

      {canManage && (
        <div className="flex items-center gap-3">
          <Button data-testid="new-action" onClick={() => setOpen((value) => !value)}>
            إضافة إجراء
          </Button>
          <span className="text-sm text-slate-600">عدد الإجراءات: {rows.length}</span>
        </div>
      )}

      {open && canManage && (
        <div
          className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
          data-testid="action-form"
        >
          <label className="flex flex-col gap-1 text-sm">
            نوع الإجراء
            <select
              data-testid="action-type"
              value={actionType}
              onChange={(event) => setActionType(event.target.value as ActionType)}
              className="rounded-lg border border-slate-300 px-3 py-2"
            >
              {ACTION_TYPES.map((type) => (
                <option key={type} value={type}>
                  {actionTypeLabel(type)}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm">
            مرتبط بإنذار (اختياري)
            <select
              data-testid="action-warning"
              value={warningId}
              onChange={(event) => setWarningId(event.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2"
            >
              <option value="">بدون ربط</option>
              {issuedWarnings.map((warning) => (
                <option key={warning.id} value={warning.id}>
                  {LEVEL_LABELS[warning.level]} — {warning.warning_type_label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm">
            ملاحظة
            <textarea
              data-testid="action-notes"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={2}
              maxLength={500}
              className="rounded-lg border border-slate-300 px-3 py-2"
            />
          </label>

          <Button
            data-testid="save-action"
            onClick={() => create.mutate()}
            disabled={create.isPending}
          >
            {create.isPending ? "جارٍ الحفظ…" : "حفظ الإجراء"}
          </Button>
        </div>
      )}

      {rows.length === 0 ? (
        <p className="rounded-xl border border-slate-200 bg-white p-6 text-slate-600 shadow-sm">
          لا توجد إجراءات مسجلة {schoolType === "GIRLS" ? "لهذه الطالبة" : "لهذا الطالب"}.
        </p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white shadow-sm">
          {rows.map((row) => (
            <li key={row.id} className="space-y-1 p-4" data-testid={`action-${row.id}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold">{row.action_type_label}</span>
                <span className="text-sm text-slate-600">
                  {row.performed_at.slice(0, 10)} · {row.performed_by_name ?? "—"}
                </span>
              </div>
              {row.warning_label && (
                <p className="text-sm text-slate-600">مرتبط بـ: {row.warning_label}</p>
              )}
              {row.notes && <p className="text-sm text-slate-700">{row.notes}</p>}
              <p className="text-sm">
                الحالة: <span data-testid={`action-status-${row.id}`}>{row.status_label}</span>
                {row.cancellation_reason && ` — ${row.cancellation_reason}`}
              </p>

              {canManage && row.status === "COMPLETED" && (
                <div className="pt-1">
                  {cancelId === row.id ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        data-testid="cancel-reason"
                        value={cancelReason}
                        onChange={(event) => setCancelReason(event.target.value)}
                        placeholder="سبب الإلغاء"
                        className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                      />
                      <Button
                        data-testid="confirm-cancel-action"
                        onClick={() => cancel.mutate(row.id)}
                        disabled={cancelReason.trim().length === 0 || cancel.isPending}
                      >
                        تأكيد الإلغاء
                      </Button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      data-testid={`cancel-action-${row.id}`}
                      onClick={() => setCancelId(row.id)}
                      className="text-sm text-red-700 underline"
                    >
                      إلغاء الإجراء
                    </button>
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

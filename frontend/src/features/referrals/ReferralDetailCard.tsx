import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { openCaseFromReferral } from "@/features/counseling/api";
import {
  type ReferralMetrics,
  acknowledgeReferral,
  addContribution,
  assignCounselor,
  cancelReferral,
  closeReferral,
  getCounselors,
  getReferral,
} from "@/features/referrals/api";
import { ReferralStatusBadge } from "@/features/referrals/ReferralsPage";
import { useActiveSchoolId } from "@/features/settings/hooks";

const METRIC_LABELS: Array<[keyof ReferralMetrics, string]> = [
  ["full_absence_days", "أيام غياب كامل"],
  ["unexcused_full_absence_days", "غياب كامل بدون عذر"],
  ["absent_periods", "حصص الغياب"],
  ["morning_late_occurrences", "مرات التأخر الصباحي"],
  ["period_late_occurrences", "مرات التأخر عن الحصص"],
];

/** تفاصيل الحالة: اللقطة وقت الإحالة مقابل المؤشرات الحالية + الملاحظات + الخط الزمني. */
export function ReferralDetailCard({
  referralId,
  onChanged,
  onClose,
}: {
  referralId: number;
  onChanged: () => void;
  onClose: () => void;
}) {
  const schoolId = useActiveSchoolId();
  const me = useMe();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [counselorId, setCounselorId] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const roles = me.data?.roles ?? [];
  const canManage = roles.some(
    (role) => role === "SCHOOL_MANAGER" || role === "VICE_PRINCIPAL",
  );
  const isCounselor = roles.includes("COUNSELOR");

  const detail = useQuery({
    queryKey: schoolScopedKey(schoolId, "referral-detail", referralId),
    queryFn: ({ signal }) => getReferral(referralId, signal),
    enabled: schoolId > 0,
  });
  const counselors = useQuery({
    queryKey: schoolScopedKey(schoolId, "referral-counselors"),
    queryFn: ({ signal }) => getCounselors(signal),
    enabled: schoolId > 0 && canManage,
  });

  const refresh = () => {
    queryClient.invalidateQueries({
      queryKey: schoolScopedKey(schoolId, "referral-detail", referralId),
    });
    onChanged();
  };

  const fail = (error: unknown) =>
    setActionError(error instanceof Error ? error.message : "تعذر تنفيذ الإجراء.");

  const assignMutation = useMutation({
    mutationFn: () => assignCounselor(referralId, Number(counselorId)),
    onSuccess: refresh,
    onError: fail,
  });
  const acknowledgeMutation = useMutation({
    mutationFn: () => acknowledgeReferral(referralId),
    onSuccess: refresh,
    onError: fail,
  });
  const closeMutation = useMutation({
    mutationFn: () => closeReferral(referralId, reason),
    onSuccess: refresh,
    onError: fail,
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelReferral(referralId, reason),
    onSuccess: refresh,
    onError: fail,
  });
  const contributionMutation = useMutation({
    mutationFn: () =>
      addContribution(referralId, {
        observation_type: "OTHER_OBSERVATION",
        notes,
      }),
    onSuccess: () => {
      setNotes("");
      refresh();
    },
    onError: fail,
  });
  const openCaseMutation = useMutation({
    mutationFn: () => openCaseFromReferral(referralId),
    onSuccess: (createdCase) => {
      refresh();
      navigate(`/counselor/cases/${createdCase.id}`);
    },
    onError: fail,
  });

  if (detail.isPending) return <Spinner />;
  if (detail.isError) return <ErrorState error={detail.error} />;
  const referral = detail.data;
  const isOpen = referral.status === "NEW" || referral.status === "ACKNOWLEDGED";
  const snapshot = referral.snapshot_at_referral ?? {};
  const current = referral.current_metrics;

  return (
    <div
      className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
      data-testid="referral-detail"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold">{referral.student.full_name}</h2>
          <p className="text-sm text-slate-600">
            {referral.student.grade_name ?? "—"} / {referral.student.section_name ?? "—"}
            <span className="mx-2">•</span>
            {referral.category_label} — {referral.reason_label}
            <span className="mx-2">•</span>
            <ReferralStatusBadge status={referral.status} label={referral.status_label} />
          </p>
        </div>
        <Button variant="secondary" onClick={onClose}>
          إغلاق العرض
        </Button>
      </div>

      {referral.description && (
        <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-800">
          {referral.description}
        </p>
      )}

      <p className="text-sm text-slate-600">
        المُحيل: {referral.created_by_name ?? "—"} ({referral.source_type_label})
        <span className="mx-2">•</span>
        المرشد: {referral.assigned_counselor_name ?? "غير معيّن"}
      </p>

      {referral.source_warning && (
        <p className="text-sm text-slate-700" data-testid="referral-source-warning">
          مرتبطة بإنذار: {referral.source_warning.warning_type} — المستوى{" "}
          {referral.source_warning.level}
        </p>
      )}

      {(current || snapshot.full_absence_days !== undefined) && (
        <section data-testid="referral-metrics">
          <h3 className="mb-2 text-sm font-bold">المؤشرات</h3>
          <div className="overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-slate-500">
                  <th className="p-3 text-start">المؤشر</th>
                  <th className="p-3 text-start">وقت الإحالة</th>
                  <th className="p-3 text-start">حاليًا</th>
                </tr>
              </thead>
              <tbody>
                {METRIC_LABELS.filter(([key]) => snapshot[key] !== undefined).map(
                  ([key, label]) => (
                    <tr key={key} className="border-b" data-testid={`metric-${key}`}>
                      <td className="p-3">{label}</td>
                      <td className="p-3">{String(snapshot[key] ?? "—")}</td>
                      <td className="p-3">{current ? String(current[key] ?? "—") : "—"}</td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section>
        <h3 className="mb-2 text-sm font-bold">
          ملاحظات على الحالة ({referral.contributions.length})
        </h3>
        <ul className="divide-y rounded-lg border border-slate-200 text-sm">
          {referral.contributions.map((contribution) => (
            <li key={contribution.id} className="p-3" data-testid={`contribution-${contribution.id}`}>
              <strong>{contribution.created_by_name ?? "—"}</strong>
              <span className="mx-2 text-xs text-slate-500">
                {contribution.observation_type_label}
              </span>
              <p className="mt-1 text-slate-700">{contribution.notes}</p>
            </li>
          ))}
          {referral.contributions.length === 0 && (
            <li className="p-3 text-slate-500">لا توجد ملاحظات بعد.</li>
          )}
        </ul>
        {isOpen && (
          <div className="mt-2 flex flex-wrap items-end gap-2">
            <label className="flex flex-1 flex-col gap-1 text-sm">
              إضافة ملاحظة
              <input
                data-testid="detail-note"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2"
              />
            </label>
            <Button
              variant="secondary"
              onClick={() => contributionMutation.mutate()}
              disabled={notes.trim() === "" || contributionMutation.isPending}
              data-testid="detail-add-note"
            >
              إضافة
            </Button>
          </div>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-bold">الخط الزمني</h3>
        <ul className="space-y-1 text-sm text-slate-600" data-testid="referral-timeline">
          {referral.events.map((event) => (
            <li key={event.id}>
              {event.event_type_label}
              {event.actor_name ? ` — ${event.actor_name}` : ""}
            </li>
          ))}
        </ul>
      </section>

      {actionError && (
        <p role="alert" className="text-sm text-red-700" data-testid="referral-action-error">
          {actionError}
        </p>
      )}

      {isOpen && (
        <div className="flex flex-wrap items-end gap-2 border-t border-slate-100 pt-3">
          {canManage && (
            <>
              <label className="flex flex-col gap-1 text-sm">
                المرشد
                <select
                  data-testid="assign-counselor"
                  value={counselorId}
                  onChange={(event) => setCounselorId(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                >
                  <option value="">اختر المرشد</option>
                  {(counselors.data?.counselors ?? []).map((counselor) => (
                    <option key={counselor.id} value={counselor.id}>
                      {counselor.name}
                    </option>
                  ))}
                </select>
              </label>
              <Button
                onClick={() => assignMutation.mutate()}
                disabled={counselorId === "" || assignMutation.isPending}
                data-testid="save-assign"
              >
                تعيين
              </Button>
            </>
          )}
          {isCounselor && referral.status === "NEW" && (
            <Button
              onClick={() => acknowledgeMutation.mutate()}
              disabled={acknowledgeMutation.isPending}
              data-testid="acknowledge-referral"
            >
              استلام الحالة
            </Button>
          )}
          {(canManage || isCounselor) && referral.counseling_case_id && (
            <Button
              variant="secondary"
              onClick={() => navigate(`/counselor/cases/${referral.counseling_case_id}`)}
              data-testid="open-counseling-case"
            >
              فتح ملف المتابعة
            </Button>
          )}
          {(roles.includes("SCHOOL_MANAGER") || isCounselor) && referral.status === "ACKNOWLEDGED" && !referral.counseling_case_id && (
            <Button
              onClick={() => openCaseMutation.mutate()}
              disabled={openCaseMutation.isPending}
              data-testid="create-counseling-case"
            >
              {openCaseMutation.isPending ? "جارٍ فتح الملف..." : "فتح ملف المتابعة"}
            </Button>
          )}
          <label className="flex flex-col gap-1 text-sm">
            سبب الإغلاق/الإلغاء
            <input
              data-testid="closure-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2"
            />
          </label>
          {(canManage || isCounselor) && (
            <Button
              variant="danger"
              onClick={() => closeMutation.mutate()}
              disabled={reason.trim() === "" || closeMutation.isPending}
              data-testid="close-referral"
            >
              إغلاق الحالة
            </Button>
          )}
          {/* الخادم يحسب can_cancel — لا نعرض زرًا سيرفضه (المنشئ قبل الاستلام
              أو الإدارة في أي وقت) */}
          {referral.can_cancel && (
            <Button
              variant="secondary"
              onClick={() => cancelMutation.mutate()}
              disabled={reason.trim() === "" || cancelMutation.isPending}
              data-testid="cancel-referral"
            >
              إلغاء الإحالة
            </Button>
          )}
        </div>
      )}

      {!isOpen && referral.closure_reason && (
        <p className="text-sm text-slate-500">
          {referral.status_label} — {referral.closure_reason}
          {referral.closed_by_name ? ` (${referral.closed_by_name})` : ""}
        </p>
      )}
    </div>
  );
}

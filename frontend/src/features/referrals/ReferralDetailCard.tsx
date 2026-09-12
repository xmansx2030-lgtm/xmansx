import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
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
  assignVicePrincipal,
  cancelReferral,
  closeReferral,
  getCounselors,
  getReferral,
  getVicePrincipals,
  startViceReview,
} from "@/features/referrals/api";
import { ReferralStatusBadge } from "@/features/referrals/ReferralsPage";
import { useActiveSchoolId, useActiveSchoolType } from "@/features/settings/hooks";
import { roleLabel } from "@/utils/roles";

const METRIC_LABELS: Array<[keyof ReferralMetrics, string]> = [
  ["full_absence_days", "أيام غياب كامل"],
  ["unexcused_full_absence_days", "غياب كامل بدون عذر"],
  ["absent_periods", "حصص الغياب"],
  ["morning_late_occurrences", "مرات التأخر الصباحي"],
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
  const schoolType = useActiveSchoolType();
  const me = useMe();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [counselorId, setCounselorId] = useState("");
  const [vicePrincipalId, setVicePrincipalId] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const detailRef = useRef<HTMLDivElement>(null);

  const roles = me.data?.roles ?? [];
  const canManage = roles.some(
    (role) => role === "SCHOOL_MANAGER" || role === "VICE_PRINCIPAL",
  );
  const isCounselor = roles.includes("COUNSELOR");
  const isManager = roles.includes("SCHOOL_MANAGER");

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
  const vicePrincipals = useQuery({
    queryKey: schoolScopedKey(schoolId, "referral-vice-principals"),
    queryFn: ({ signal }) => getVicePrincipals(signal),
    enabled: schoolId > 0 && isManager,
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
  const assignViceMutation = useMutation({
    mutationFn: () => assignVicePrincipal(referralId, Number(vicePrincipalId)),
    onSuccess: refresh,
    onError: fail,
  });
  const startViceReviewMutation = useMutation({
    mutationFn: () => startViceReview(referralId),
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
  const detailId = detail.data?.id;

  // البطاقة تقع بعد الجدول في أكثر من شاشة. بدون نقل التركيز إليها تبدو نقرة
  // «التفاصيل» وكأنها لم تستجب، خصوصًا مع قوائم الإحالات الطويلة.
  // يبقى الـ Hook قبل حالات التحميل كي لا يتغير ترتيبه بين render وآخر.
  useEffect(() => {
    if (!detailId) return;
    detailRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    detailRef.current?.focus({ preventScroll: true });
  }, [detailId]);

  useEffect(() => {
    const suggested =
      detail.data?.assigned_counselor_id ?? detail.data?.recommended_counselor_id;
    setCounselorId(suggested ? String(suggested) : "");
  }, [detail.data?.assigned_counselor_id, detail.data?.recommended_counselor_id]);

  if (detail.isPending) return <Spinner />;
  if (detail.isError) return <ErrorState error={detail.error} />;
  const referral = detail.data;
  const isOpen = referral.status !== "CLOSED" && referral.status !== "CANCELLED";
  const snapshot = referral.snapshot_at_referral ?? {};
  const current = referral.current_metrics;

  return (
    <div
      ref={detailRef}
      id="referral-details"
      tabIndex={-1}
      className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
      data-testid="referral-detail"
    >
      <div className="flex flex-col items-stretch justify-between gap-3 sm:flex-row sm:items-center">
        <div className="min-w-0">
          <h2 className="break-words text-lg font-bold">{referral.student.full_name}</h2>
          <p className="mt-1 break-words text-sm leading-7 text-slate-600">
            {referral.student.grade_name ?? "—"} / {referral.student.section_name ?? "—"}
            <span className="mx-2">•</span>
            {referral.category_label} — {referral.reason_label}
            <span className="mx-2">•</span>
            <ReferralStatusBadge status={referral.status} label={referral.status_label} />
          </p>
        </div>
        <Button variant="secondary" className="w-full justify-center sm:w-auto" onClick={onClose}>
          إغلاق العرض
        </Button>
      </div>

      {referral.description && (
        <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-800">
          {referral.description}
        </p>
      )}

      <div className="grid gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-3 text-sm sm:grid-cols-3" data-testid="referral-routing">
        <p><span className="block text-xs font-bold text-slate-500">المُحيل</span><strong>{referral.created_by_name ?? "—"}</strong> ({referral.source_type_label})</p>
        <p><span className="block text-xs font-bold text-slate-500">الوكيل المسؤول</span><strong>{referral.assigned_vice_principal_name ?? "لم يُعيّن بعد"}</strong></p>
        <p><span className="block text-xs font-bold text-slate-500">{roleLabel("COUNSELOR", schoolType)}</span><strong>{referral.assigned_counselor_name ?? "لم تُحوّل للمرشد"}</strong></p>
      </div>

      {referral.source_warning && (
        <p className="text-sm text-slate-700" data-testid="referral-source-warning">
          مرتبطة بإنذار: {referral.source_warning.warning_type} — المستوى{" "}
          {referral.source_warning.level}
        </p>
      )}

      {(current || snapshot.full_absence_days !== undefined) && (
        <section data-testid="referral-metrics">
          <h3 className="mb-2 text-sm font-bold">المؤشرات</h3>
          <div className="grid gap-2 md:hidden" data-testid="referral-metrics-list">
            {METRIC_LABELS.filter(([key]) => snapshot[key] !== undefined).map(
              ([key, label]) => (
                <article
                  key={key}
                  className="rounded-xl border border-slate-200 bg-slate-50/70 p-3"
                  data-testid={`metric-card-${key}`}
                >
                  <p className="text-sm font-bold text-slate-800">{label}</p>
                  <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
                    <div className="rounded-lg bg-white p-2">
                      <dt className="text-xs text-slate-500">وقت الإحالة</dt>
                      <dd className="mt-1 font-black text-slate-900">{String(snapshot[key] ?? "—")}</dd>
                    </div>
                    <div className="rounded-lg bg-white p-2">
                      <dt className="text-xs text-slate-500">حاليًا</dt>
                      <dd className="mt-1 font-black text-slate-900">{current ? String(current[key] ?? "—") : "—"}</dd>
                    </div>
                  </dl>
                </article>
              ),
            )}
          </div>
          <div className="hidden overflow-x-auto rounded-lg border border-slate-200 md:block">
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
          <div className="mt-2 flex flex-col items-stretch gap-2 sm:flex-row sm:items-end">
            <label className="flex min-w-0 flex-1 flex-col gap-1 text-sm">
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
              className="w-full justify-center sm:w-auto"
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
        <div className="grid gap-2 border-t border-slate-100 pt-3 sm:flex sm:flex-wrap sm:items-end">
          {referral.can_assign_vice_principal && (
            <>
              <label className="flex min-w-0 flex-col gap-1 text-sm">
                الوكيل المسؤول
                <select
                  data-testid="assign-vice-principal"
                  value={vicePrincipalId}
                  onChange={(event) => setVicePrincipalId(event.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2"
                >
                  <option value="">اختر الوكيل</option>
                  {(vicePrincipals.data?.vice_principals ?? []).map((vice) => (
                    <option key={vice.id} value={vice.id}>{vice.name}</option>
                  ))}
                </select>
              </label>
              <Button
                variant="secondary"
                className="w-full justify-center sm:w-auto"
                onClick={() => assignViceMutation.mutate()}
                disabled={vicePrincipalId === "" || assignViceMutation.isPending}
                data-testid="save-assign-vice"
              >
                إسناد للوكيل
              </Button>
            </>
          )}
          {referral.can_start_vice_review && (
            <Button
              variant="secondary"
              className="w-full justify-center border-violet-200 text-violet-800 sm:w-auto"
              onClick={() => startViceReviewMutation.mutate()}
              disabled={startViceReviewMutation.isPending}
              data-testid="start-vice-review"
            >
              {startViceReviewMutation.isPending ? "جارٍ البدء..." : "بدء معالجة الإحالة"}
            </Button>
          )}
          {referral.can_forward_to_counselor && (
            <>
              <label className="flex min-w-0 flex-col gap-1 text-sm">
                {roleLabel("COUNSELOR", schoolType)}
                <select
                  data-testid="assign-counselor"
                  value={counselorId}
                  onChange={(event) => setCounselorId(event.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2"
                >
                  <option value="">اختر {roleLabel("COUNSELOR", schoolType)}</option>
                  {(counselors.data?.counselors ?? []).map((counselor) => (
                    <option key={counselor.id} value={counselor.id}>
                      {counselor.name}
                      {counselor.id === referral.recommended_counselor_id
                        ? " — المسؤول عن الفصل"
                        : ""}
                    </option>
                  ))}
                </select>
                {referral.recommended_counselor_name && (
                  <span className="text-xs font-bold text-teal-700">
                    المقترح حسب فصل الطالب: {referral.recommended_counselor_name}
                  </span>
                )}
              </label>
              <Button
                className="w-full justify-center sm:w-auto"
                onClick={() => assignMutation.mutate()}
                disabled={counselorId === "" || assignMutation.isPending}
                data-testid="save-assign"
              >
                {referral.status === "REFERRED" ? "تغيير المرشد" : "تحويل للمرشد"}
              </Button>
            </>
          )}
          {referral.can_acknowledge && (
            <Button
              className="w-full justify-center sm:w-auto"
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
              className="w-full justify-center sm:w-auto"
              onClick={() => navigate(`/counselor/cases/${referral.counseling_case_id}`)}
              data-testid="open-counseling-case"
            >
              فتح ملف المتابعة
            </Button>
          )}
          {(roles.includes("SCHOOL_MANAGER") || isCounselor) && referral.status === "ACKNOWLEDGED" && !referral.counseling_case_id && (
            <Button
              className="w-full justify-center sm:w-auto"
              onClick={() => openCaseMutation.mutate()}
              disabled={openCaseMutation.isPending}
              data-testid="create-counseling-case"
            >
              {openCaseMutation.isPending ? "جارٍ فتح الملف..." : "فتح ملف المتابعة"}
            </Button>
          )}
          {(referral.can_close || referral.can_cancel) && (
            <label className="flex min-w-0 flex-col gap-1 text-sm sm:min-w-56 sm:flex-1">
              سبب الإغلاق/الإلغاء
              <input
                data-testid="closure-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2"
              />
            </label>
          )}
          {referral.can_close && (
            <Button
              variant="danger"
              className="w-full justify-center sm:w-auto"
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
              className="w-full justify-center sm:w-auto"
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

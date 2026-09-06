import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { schoolScopedKey } from "@/features/auth/useMe";
import {
  type DuplicateDetails,
  contributeToOpenCase,
  createReferral,
  getReferralOptions,
} from "@/features/referrals/api";
import { useActiveSchoolId, useActiveSchoolType } from "@/features/settings/hooks";
import { roleLabel } from "@/utils/roles";

/** نموذج الإحالة: الفئات والأسباب تأتي من الخادم حسب دور المستخدم (بند 120/121).
 *
 *  عند اكتشاف تكرار لا نفتح حالة ثانية: نعرض الحالة القائمة والخيار الافتراضي
 *  «إضافة ملاحظة إليها» (بند 33/122).
 */
export function ReferralCreateCard({
  student,
  sourceWarningId,
  onCreated,
  onContributed,
  onCancel,
}: {
  student: { id: number; name: string };
  sourceWarningId?: number;
  onCreated: (referralId: number) => void;
  onContributed?: (referralId: number) => void;
  onCancel: () => void;
}) {
  const schoolId = useActiveSchoolId();
  const schoolType = useActiveSchoolType();
  const [category, setCategory] = useState("");
  const [reason, setReason] = useState("");
  const [description, setDescription] = useState("");
  const [duplicate, setDuplicate] = useState<DuplicateDetails | null>(null);
  const [contributionNotes, setContributionNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const options = useQuery({
    queryKey: schoolScopedKey(schoolId, "referral-options"),
    queryFn: ({ signal }) => getReferralOptions(signal),
    enabled: schoolId > 0,
  });

  const categories = options.data?.categories ?? [];
  const activeCategory = categories.find((item) => item.value === category);
  const reasons = activeCategory?.reasons ?? [];
  const requiresDescription = reason.startsWith("OTHER_");

  const createMutation = useMutation({
    mutationFn: () =>
      createReferral({
        student_id: student.id,
        category,
        reason_code: reason,
        description,
        source_warning_id: sourceWarningId ?? null,
      }),
    onSuccess: (referral) => onCreated(referral.id),
    onError: (mutationError: unknown) => {
      if (
        mutationError instanceof ApiError &&
        mutationError.code === "DUPLICATE_OPEN_REFERRAL"
      ) {
        setDuplicate(mutationError.details as unknown as DuplicateDetails);
        setError(null);
        return;
      }
      setError(
        mutationError instanceof Error ? mutationError.message : "تعذر إنشاء الإحالة.",
      );
    },
  });

  const contributionMutation = useMutation({
    // الخادم يحل الحالة المفتوحة من (الطالب، الفئة) — لا نمرر معرف إحالة لا نراها
    mutationFn: () =>
      contributeToOpenCase({
        student_id: student.id,
        category,
        observation_type: observationTypeFor(category),
        notes: contributionNotes,
      }),
    onSuccess: (result) => {
      setDuplicate(null);
      (onContributed ?? onCreated)(result.referral_id);
    },
    onError: (mutationError: unknown) =>
      setError(
        mutationError instanceof Error ? mutationError.message : "تعذر إضافة الملاحظة.",
      ),
  });

  const ready =
    category !== "" && reason !== "" && (!requiresDescription || description.trim() !== "");

  if (duplicate) {
    return (
      <div
        className="space-y-3 rounded-xl border border-amber-300 bg-amber-50 p-4 shadow-sm"
        data-testid="referral-duplicate"
      >
        <h2 className="font-bold">يوجد {schoolType === "GIRLS" ? "للطالبة" : "للطالب"} ملف متابعة مفتوح في نفس الفئة</h2>
        <p className="text-sm text-slate-700">
          الأفضل إضافة ملاحظتك إلى الحالة القائمة بدل فتح حالة جديدة، {schoolType === "GIRLS" ? "لتجدها" : "ليجدها"} {roleLabel("COUNSELOR", schoolType)}
          مجتمعة.
        </p>
        <label className="flex flex-col gap-1 text-sm">
          ملاحظتك
          <textarea
            data-testid="duplicate-notes"
            value={contributionNotes}
            onChange={(event) => setContributionNotes(event.target.value)}
            rows={3}
            className="rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            onClick={() => contributionMutation.mutate()}
            disabled={contributionNotes.trim() === "" || contributionMutation.isPending}
            data-testid="add-contribution"
          >
            {contributionMutation.isPending ? "جارٍ الإضافة..." : "إضافة ملاحظة"}
          </Button>
          {/* مخرج من الطريق المسدود: لو أُغلقت الحالة القائمة لحظتها فالإضافة
              تفشل أبدًا، بينما إحالة جديدة صارت مقبولة */}
          <Button
            variant="secondary"
            onClick={() => {
              setDuplicate(null);
              setError(null);
            }}
            data-testid="back-to-form"
          >
            العودة إلى النموذج
          </Button>
          <Button variant="secondary" onClick={onCancel}>
            إلغاء
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
      data-testid="referral-create"
    >
      <h2 className="font-bold">تحويل {schoolType === "GIRLS" ? "الطالبة" : "الطالب"} إلى {roleLabel("COUNSELOR", schoolType)}</h2>
      <p className="text-sm text-slate-600">
        {schoolType === "GIRLS" ? "الطالبة" : "الطالب"}: <strong data-testid="referral-student">{student.name}</strong>
      </p>
      <p className="text-xs text-slate-500">
        اكتب ملاحظة واقعية قابلة للملاحظة (مثال: «نام داخل الحصة ثلاث مرات هذا
        الأسبوع») — الإحالة طلب متابعة وليست تشخيصًا.
      </p>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          الفئة
          <select
            data-testid="referral-category"
            value={category}
            onChange={(event) => {
              setCategory(event.target.value);
              setReason("");
            }}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">اختر الفئة</option>
            {categories.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          السبب
          <select
            data-testid="referral-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            disabled={category === ""}
            className="rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">اختر السبب</option>
            {reasons.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="flex flex-col gap-1 text-sm">
        وصف الملاحظة {requiresDescription ? "(مطلوب)" : "(اختياري)"}
        <textarea
          data-testid="referral-description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          rows={3}
          className="rounded-lg border border-slate-300 px-3 py-2"
        />
      </label>

      {error && (
        <p role="alert" className="text-sm text-red-700" data-testid="referral-error">
          {error}
        </p>
      )}

      <div className="flex gap-2">
        <Button
          onClick={() => createMutation.mutate()}
          disabled={!ready || createMutation.isPending}
          data-testid="save-referral"
        >
          {createMutation.isPending ? "جارٍ الإرسال..." : "إرسال الإحالة"}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          إلغاء
        </Button>
      </div>
    </div>
  );
}

function observationTypeFor(category: string): string {
  if (category === "ACADEMIC") return "ACADEMIC_OBSERVATION";
  if (category === "CLASSROOM_BEHAVIOR") return "CLASSROOM_OBSERVATION";
  if (category === "ATTENDANCE") return "ATTENDANCE_OBSERVATION";
  return "OTHER_OBSERVATION";
}

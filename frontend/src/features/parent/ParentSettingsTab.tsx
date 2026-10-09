import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { PageSkeleton } from "@/components/Skeleton";
import { TextField } from "@/components/TextField";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { getParentSettings, setParentSettings } from "@/features/parent/api";
import { surface } from "@/features/parent/shared";

const STAT_LABELS: Record<string, string> = {
  registered_parents: "أولياء الأمور المسجلون",
  coverage_percent: "نسبة تغطية الطلاب",
  pending_registrations: "طلبات التسجيل المعلقة",
  relations_needing_review: "علاقات تحتاج مراجعة",
  unactivated_accounts: "حسابات غير مفعلة",
  average_processing_seconds: "متوسط المعالجة بالثواني",
  student_count: "طلاب المدرسة",
  registered_guardians: "أولياء الأمور المسجلون",
  linked_students: "الطلاب المرتبطون",
  coverage_percentage: "نسبة تغطية الطلاب",
  pending_requests: "طلبات التسجيل المعلقة",
  contact_review_relations: "علاقات تحتاج مراجعة",
  inactive_accounts: "حسابات غير مفعلة",
  average_processing_hours: "متوسط المعالجة بالساعات",
  pending_excuses: "الأعذار المعلقة",
  active_relations: "العلاقات المعتمدة",
  total_requests: "طلبات التسجيل",
  suspended_relations: "العلاقات المعلقة",
};
export function ParentSettingsTab() {
  const me = useMe();
  const schoolId = me.data?.active_school?.id ?? 0;
  const queryClient = useQueryClient();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [copied, setCopied] = useState(false);
  const [qrError, setQrError] = useState(false);
  const key = schoolScopedKey(schoolId, "parents", "settings");
  const settings = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => getParentSettings(signal),
    enabled: !!schoolId,
  });
  const toggle = useMutation({
    mutationFn: setParentSettings,
    onSuccess: (value) => queryClient.setQueryData(key, value),
  });
  const registrationUrl = settings.data?.registration_url
    ? new URL(settings.data.registration_url, window.location.origin).href
    : "";
  useEffect(() => {
    if (registrationUrl && canvas.current)
      void QRCode.toCanvas(canvas.current, registrationUrl, {
        width: 220,
        margin: 2,
        errorCorrectionLevel: "M",
      }).catch(() => setQrError(true));
  }, [registrationUrl]);
  if (settings.isPending)
    return <PageSkeleton label="جارٍ تحميل تسجيل أولياء الأمور" />;
  if (settings.isError) return <ErrorState error={settings.error} />;
  return (
    <div className="space-y-4">
      <section className={surface}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-black">تسجيل أولياء الأمور</h2>
            <p className="mt-2 text-sm leading-7 text-slate-600">
              الرابط يحدد المدرسة فقط. تراجع الإدارة كل علاقة قبل التفعيل.
            </p>
          </div>
          {me.data?.roles.includes("SCHOOL_MANAGER") && (
            <Button
              variant={settings.data.enabled ? "secondary" : "primary"}
              loading={toggle.isPending}
              onClick={() => toggle.mutate(!settings.data.enabled)}
            >
              {settings.data.enabled
                ? "إيقاف استقبال الطلبات"
                : "تفعيل استقبال الطلبات"}
            </Button>
          )}
        </div>
        <p className="mt-3 text-sm font-bold">
          {settings.data.enabled ? "التسجيل مفعل" : "التسجيل متوقف"}
        </p>
        {toggle.isError && <ErrorState error={toggle.error} />}
        <div className="mt-5 grid items-center gap-4 sm:grid-cols-[auto_minmax(0,1fr)]">
          <div>
            <canvas
              ref={canvas}
              aria-label="رمز QR لتسجيل أولياء الأمور"
              className="mx-auto max-w-full"
            />
            {qrError && (
              <Alert tone="warning" title="تعذر إنشاء QR">
                يمكنك مشاركة الرابط مباشرة.
              </Alert>
            )}
          </div>
          <div className="min-w-0 space-y-3">
            <TextField
              label="رابط التسجيل"
              dir="ltr"
              readOnly
              value={registrationUrl}
            />
            <Button
              variant="secondary"
              onClick={() =>
                void navigator.clipboard
                  ?.writeText(registrationUrl)
                  .then(() => setCopied(true))
              }
            >
              {copied ? "تم نسخ الرابط" : "نسخ الرابط"}
            </Button>
            <Link
              to="/parent-management"
              className="inline-flex min-h-11 items-center px-3 font-bold text-teal-800"
            >
              إدارة أولياء الأمور
            </Link>
          </div>
        </div>
      </section>
      <section className={surface}>
        <h2 className="font-black">إحصائيات البوابة</h2>
        <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
          {Object.entries(settings.data.stats)
            .filter(([name]) => STAT_LABELS[name])
            .map(([name, value]) => (
              <div key={name}>
                <dt className="text-xs text-slate-500">{STAT_LABELS[name]}</dt>
                <dd className="mt-1 text-2xl font-black">
                  {value}
                  {name.includes("percentage") || name === "coverage_percent"
                    ? "%"
                    : ""}
                </dd>
              </div>
            ))}
        </dl>
      </section>
    </div>
  );
}

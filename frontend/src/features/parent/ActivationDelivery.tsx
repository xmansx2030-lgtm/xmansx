import { Alert } from "@/components/Alert";
import type {
  ActivationDeliveryRecord,
  ActivationDeliveryStatus,
} from "@/features/parent/api";
import { dateTime } from "@/features/parent/shared";

const labels: Record<ActivationDeliveryStatus, string> = {
  PENDING: "بانتظار التسليم",
  SENDING: "جارٍ التسليم",
  SENT: "قبل مزود الإرسال رسالة التفعيل",
  FAILED: "تعذر إرسال رسالة التفعيل",
  UNKNOWN: "نتيجة إرسال التفعيل غير مؤكدة",
  MANUAL: "صدر رابط للتسليم الموثق",
};

export function ActivationDeliveryResult({
  status,
}: {
  status?: ActivationDeliveryStatus;
}) {
  if (!status) return null;
  const uncertain = status === "FAILED" || status === "UNKNOWN";
  return (
    <Alert
      tone={uncertain ? "warning" : status === "SENT" ? "success" : "info"}
      title={labels[status]}
      live
    >
      {uncertain
        ? "راجع نتيجة التسليم مع مقدم الطلب. لا توجد إعادة إرسال تلقائية؛ يمكن إصدار تفعيل جديد أو اختيار التسليم الموثق بعد تحقق حديث من صاحب الصفة."
        : status === "SENT"
          ? "قبول المزود للإرسال لا يؤكد وصول الرسالة أو تفعيل الحساب."
          : status === "MANUAL"
            ? "سلم الرابط فقط لصاحب الصفة الذي جرى التحقق منه، ثم تابِع تفعيل الحساب."
            : "تابِع نتيجة التسليم قبل إصدار تفعيل آخر."}
    </Alert>
  );
}

export function ActivationDeliveryHistory({
  records,
}: {
  records: ActivationDeliveryRecord[];
}) {
  if (!records.length) return null;
  return (
    <section
      className="space-y-3 rounded-xl border border-slate-200 p-4"
      aria-label="سجل تسليم التفعيل"
    >
      <h2 className="font-bold">سجل تسليم التفعيل</h2>
      <ul className="space-y-3 text-sm">
        {records.map((record) => (
          <li key={record.id} className="rounded-lg bg-slate-50 p-3">
            <p className="font-bold">{labels[record.delivery_status]}</p>
            <p className="mt-1 text-xs text-slate-600">
              الإصدار: {dateTime(record.created_at)} · الانتهاء:{" "}
              {dateTime(record.expires_at)}
            </p>
            {record.used_at && (
              <p className="mt-1 text-xs">
                تم التفعيل: {dateTime(record.used_at)}
              </p>
            )}
            {record.revoked_at && (
              <p className="mt-1 text-xs">
                ألغي الرابط: {dateTime(record.revoked_at)}
              </p>
            )}
            {record.failure_code && (
              <p className="mt-1 text-xs">
                رمز نتيجة التسليم: <span dir="ltr">{record.failure_code}</span>
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

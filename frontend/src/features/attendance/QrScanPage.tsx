import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { resolveQr } from "@/features/attendance/api";

/** ‏/qr/:token — يحل الرمز إلى فصل داخل مدرسة الجلسة الحالية ثم يفتح التحضير.
 *  الرمز لا يمنح صلاحية: بلا تسجيل دخول وعضوية ودور معلم يرفض الخادم. */
export function QrScanPage() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [error, setError] = useState<unknown>(null);
  const requested = useRef(false);

  useEffect(() => {
    if (!token || requested.current) return;
    requested.current = true; // StrictMode يشغّل effect مرتين — طلب واحد يكفي
    resolveQr(token)
      .then((section) => {
        navigate(`/attendance/section/${section.id}`, { replace: true });
      })
      .catch((err: unknown) => setError(err));
  }, [token, navigate]);

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      {error == null ? (
        <Spinner label="جارٍ التحقق من رمز الفصل..." />
      ) : (
        <div className="space-y-3">
          <ErrorState error={error} />
          <p>
            <Link to="/" className="text-blue-700 underline">
              العودة للرئيسية واختيار الفصل يدويًا
            </Link>
          </p>
        </div>
      )}
    </section>
  );
}

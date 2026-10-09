import { Link } from "react-router-dom";

import { Alert } from "@/components/Alert";
import { useMe } from "@/features/auth/useMe";

export function SchoolEmailVerificationNotice() {
  const me = useMe();
  if (!me.data?.school_email_verification_pending || !me.data.school_recovery_email_enabled) return null;
  return (
    <Alert tone="warning" title="بانتظار توثيق بريدك الإلكتروني" className="mb-5">
      يمكنك متابعة عملك. افتح رابط التحقق في بريدك لتفعيل استعادة كلمة المرور.{" "}
      <Link to="/account/recovery-email" className="inline-flex min-h-11 items-center font-bold underline">
        توثيق البريد وإعادة الإرسال
      </Link>
    </Alert>
  );
}

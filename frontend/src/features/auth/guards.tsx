import { Navigate, Outlet } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Spinner } from "@/components/Spinner";
import { useMe } from "@/features/auth/useMe";

function FullPageSpinner() {
  return (
    <div className="flex min-h-dvh items-center justify-center">
      <Spinner label="جارٍ التحميل..." />
    </div>
  );
}

/** غير مسجل → /login، وكلمة مؤقتة → شاشة التغيير الإجبارية.
 *  (الحماية الحقيقية على الـ Backend — هذا UX فقط) */
export function RequireAuth() {
  const me = useMe();

  if (me.isPending) return <FullPageSpinner />;
  if (me.isError) {
    if (me.error instanceof ApiError && (me.error.status === 401 || me.error.status === 403)) {
      return <Navigate to="/login" replace />;
    }
    throw me.error; // أخطاء أخرى → صفحة الخطأ العامة
  }
  if (me.data.must_change_password) {
    return <Navigate to="/change-password" replace />;
  }
  return <Outlet />;
}

/** مسجل بلا مدرسة نشطة → اختيار المدرسة (أو رسالة عند غياب العضويات). */
export function RequireActiveSchool() {
  const me = useMe();

  if (me.isPending) return <FullPageSpinner />;
  if (me.isError) return <Navigate to="/login" replace />;

  if (me.data.active_school === null) {
    if (me.data.memberships.length > 0 || me.data.invitations.length > 0) {
      return <Navigate to="/select-school" replace />;
    }
    return (
      <div className="flex min-h-dvh items-center justify-center p-6 text-center">
        <div>
          <h1 className="mb-2 text-xl font-bold">لا توجد مدارس مرتبطة بحسابك</h1>
          <p className="text-slate-600">تواصل مع إدارة مدرستك لإضافتك.</p>
        </div>
      </div>
    );
  }
  return <Outlet />;
}

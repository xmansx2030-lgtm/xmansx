import { Navigate, Outlet } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Spinner } from "@/components/Spinner";
import { useMe } from "@/features/auth/useMe";
import type { SchoolCapability, SchoolRole } from "@/types/auth";

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
  if (me.data.is_platform_admin) return <Navigate to="/platform" replace />;

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

/** إدارة المنصة صلاحية عالمية؛ لا تحتاج مدرسة نشطة ولا عضوية مدرسية. */
export function RequirePlatformAdmin() {
  const me = useMe();

  if (me.isPending) return <FullPageSpinner />;
  if (me.isError) return <Navigate to="/login" replace />;
  if (!me.data.is_platform_admin) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}

function roleWorkspace(roles: SchoolRole[]) {
  if (roles.includes("SCHOOL_MANAGER") || roles.includes("VICE_PRINCIPAL")) {
    return "/dashboard";
  }
  if (roles.includes("COUNSELOR")) return "/counselor";
  if (roles.includes("GATE_GUARD")) return "/gate";
  return "/";
}

/**
 * يمنع المسارات المباشرة من عرض قالب لا يخص دور المستخدم ثم إغراقه بأخطاء 403.
 * الخادم يبقى مصدر الإنفاذ؛ هذه الطبقة تختار محطة العمل المفيدة للمستخدم فقط.
 */
export function RequireSchoolRoles({
  allowedRoles,
  allowedCapabilities = [],
}: {
  allowedRoles: SchoolRole[];
  allowedCapabilities?: SchoolCapability[];
}) {
  const me = useMe();

  if (me.isPending) return <FullPageSpinner />;
  if (me.isError) return <Navigate to="/login" replace />;
  const hasRole = me.data.roles.some((role) => allowedRoles.includes(role));
  const hasCapability = (me.data.capabilities ?? []).some((capability) =>
    allowedCapabilities.includes(capability),
  );
  if (hasRole || hasCapability) return <Outlet />;

  return <Navigate to={roleWorkspace(me.data.roles)} replace />;
}

import { Navigate } from "react-router-dom";

import { useMe } from "@/features/auth/useMe";
import { LandingPage } from "@/features/public/LandingPage";

/** الصفحة العامة تبقى متاحة للزائر، والمسجل يُعاد إلى مساحة عمله بلا وميض تسجيل. */
export function PublicRootPage() {
  const me = useMe();

  if (me.isPending) {
    return (
      <div role="status" aria-label="جارٍ التحقق من الحساب" className="grid min-h-dvh place-items-center bg-[#061916] px-6 text-white">
        <div className="flex items-center gap-3 rounded-2xl border border-teal-300/15 bg-white/[0.04] px-5 py-4">
          <span aria-hidden="true" className="size-2 animate-pulse rounded-full bg-teal-300" />
          <p className="text-sm font-bold text-teal-100">منصة المواظبة</p>
        </div>
      </div>
    );
  }
  if (me.isSuccess) {
    if (me.data.must_change_password) return <Navigate to="/change-password" replace />;
    if (me.data.is_platform_admin) return <Navigate to="/platform" replace />;
    if (me.data.active_school) return <Navigate to="/workspace" replace />;
    return <Navigate to="/select-school" replace />;
  }
  return <LandingPage />;
}

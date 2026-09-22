import { Navigate } from "react-router-dom";

import { useMe } from "@/features/auth/useMe";
import { LandingPage } from "@/features/public/LandingPage";

/** الصفحة العامة تبقى متاحة للزائر، والمسجل يُعاد إلى مساحة عمله بلا وميض تسجيل. */
export function PublicRootPage() {
  const me = useMe();

  if (me.isPending) {
    return (
      <div className="grid min-h-dvh place-items-center bg-[#061916] text-white">
        <p className="animate-pulse text-sm font-bold text-teal-100">منصة المواظبة</p>
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

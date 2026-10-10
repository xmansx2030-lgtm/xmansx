import { Navigate } from "react-router-dom";

import { useMe } from "@/features/auth/useMe";
import { authenticatedDestination } from "@/features/auth/destination";
import { LandingPage } from "@/features/public/LandingPage";

/** المحتوى العام لا ينتظر API المصادقة؛ المسجل يُعاد إلى مساحة عمله كالمعتاد. */
export function PublicRootPage() {
  const me = useMe();

  if (me.isSuccess) {
    return <Navigate to={authenticatedDestination(me.data)} replace />;
  }
  return <LandingPage />;
}

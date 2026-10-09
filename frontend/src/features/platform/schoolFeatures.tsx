import { useQuery } from "@tanstack/react-query";
import { Fingerprint, HeartHandshake, LockKeyhole, MessageSquareMore } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiRequest } from "@/api/client";
import { adaptivePollingInterval } from "@/app/polling";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import type { SchoolFeature, SchoolFeatureState } from "@/types/schoolFeatures";
export type { SchoolFeature, SchoolFeatures, SchoolFeatureState } from "@/types/schoolFeatures";

export const SCHOOL_FEATURES = [
  { key: "ABSENCE_SMS", label: "رسائل الغياب", description: "إرسال رسائل الغياب إلى أولياء الأمور عبر مزود المدرسة.", icon: MessageSquareMore },
  { key: "PARENT_PORTAL", label: "بوابة ولي الأمر", description: "تسجيل الأسرة ومراجعة العلاقات والطلبات والتواصل مع المدرسة.", icon: HeartHandshake },
  { key: "BIOMETRIC_DEVICES", label: "الربط مع أجهزة البصمة", description: "ربط أجهزة الحضور بالجسر ومزامنة قوائم الطلاب.", icon: Fingerprint },
] as const;

export function featureForPath(path: string, search = ""): SchoolFeature | null {
  path = path.replace(/\/+$/, "") || "/";
  if (path === "/parent-management") return "PARENT_PORTAL";
  if (path === "/attendance/absence-messages") return "ABSENCE_SMS";
  if (path === "/devices" || path.startsWith("/devices/")) return "BIOMETRIC_DEVICES";
  if (path === "/settings") {
    const section = new URLSearchParams(search).get("section");
    if (section === "parents") return "PARENT_PORTAL";
    if (section === "sms") return "ABSENCE_SMS";
  }
  return null;
}

export function useSchoolFeatures() {
  const me = useMe();
  const schoolId = me.data?.active_school?.id ?? 0;
  const state = useQuery({
    queryKey: schoolScopedKey(schoolId, "feature-access"),
    queryFn: ({ signal }) => apiRequest<SchoolFeatureState>("/school/features/", { signal }),
    enabled: !!schoolId && !!me.data?.school_features,
    staleTime: 15_000,
    refetchInterval: adaptivePollingInterval(30_000),
    refetchIntervalInBackground: false,
  });
  return state.data?.school_id === schoolId ? state.data.features : me.data?.school_features;
}

export function FeatureSubscriptionNotice({ feature }: { feature: SchoolFeature }) {
  const me = useMe();
  const item = SCHOOL_FEATURES.find((item) => item.key === feature)!;
  const Icon = item.icon;
  return <section role="region" aria-label={`${item.label} تتطلب اشتراكًا`} className="mx-auto w-full max-w-xl rounded-3xl border border-slate-200 bg-white p-6 text-center shadow-sm sm:p-10">
    <span className="mx-auto grid size-16 place-items-center rounded-2xl bg-slate-100 text-slate-400"><Icon aria-hidden size={30} /></span>
    <span className="mx-auto mt-5 inline-flex items-center gap-2 rounded-full bg-amber-50 px-3 py-1.5 text-xs font-bold text-amber-800"><LockKeyhole aria-hidden size={14} />يلزم اشتراك</span>
    <h2 className="mt-4 text-xl font-black text-slate-900">{item.label}</h2>
    <p className="mt-3 text-sm leading-7 text-slate-600">هذه الميزة تتطلب اشتراكًا وتفعيلًا من إدارة المنصة لمدرستك.</p>
    <p className="mt-2 text-sm leading-7 text-slate-500">{item.description}</p>
    {me.data?.roles.includes("SCHOOL_MANAGER") ? <Link className="mt-6 inline-flex min-h-11 items-center justify-center rounded-xl bg-teal-700 px-5 text-sm font-bold text-white hover:bg-teal-800" to="/subscription">عرض اشتراك المدرسة</Link> : <p className="mt-5 text-sm font-bold text-teal-800">تواصل مع مدير المدرسة لطلب تفعيل الميزة.</p>}
  </section>;
}

export function SchoolFeatureBoundary({ children }: { children: ReactNode }) {
  const location = useLocation();
  const features = useSchoolFeatures();
  const feature = featureForPath(location.pathname, location.search);
  if (location.pathname.replace(/\/+$/, "") === "/settings") return children;
  if (feature && features?.[feature] === false) return <FeatureSubscriptionNotice feature={feature} />;
  return children;
}

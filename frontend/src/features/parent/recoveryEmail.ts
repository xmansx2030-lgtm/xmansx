import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ensureCsrfCookie } from "@/api/auth";
import { apiRequest } from "@/api/client";
import { useMe } from "@/features/auth/useMe";

export const RECOVERY_EMAIL_DESCRIPTION =
  "سيُستخدم هذا البريد لاستعادة كلمة المرور عند نسيانها، ولن تُرسل إليه إشعارات الطلاب أو الرسائل الإعلانية.";
export const RECOVERY_REQUEST_MESSAGE =
  "إذا كان الحساب مسجلاً وله بريد إلكتروني موثق، فسيتم إرسال رابط استعادة كلمة المرور إليه.";

/** The backend applies authoritative NFC/casefold validation to trimmed form input. */
export function normalizeRecoveryEmail(email: string): string {
  return email.trim().toLowerCase();
}

export function recoveryEmailError(email: string): string {
  const value = normalizeRecoveryEmail(email);
  if (!value) return "البريد الإلكتروني مطلوب.";
  if (value.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value))
    return "صيغة البريد الإلكتروني غير صحيحة.";
  return "";
}

export interface RecoveryEmailStatus {
  verified: boolean;
  verification_required: boolean;
  email_masked: string;
  pending_email_masked: string;
  delivery_status: "PENDING" | "SENDING" | "SUBMITTED_TO_PROVIDER" | "FAILED" | "UNKNOWN" | "CANCELLED" | null;
  enabled: boolean;
}

const EMAIL_PATH = "/parent/recovery-email/";
const RESET_PATH = "/auth/parent-password-recovery/";
export const recoveryEmailKey = (userId?: number) =>
  ["parent-recovery-email", userId] as const;

export function useRecoveryEmailStatus() {
  const me = useMe();
  return useQuery({
    queryKey: recoveryEmailKey(me.data?.id),
    queryFn: ({ signal }) => apiRequest<RecoveryEmailStatus>(EMAIL_PATH, { signal }),
    enabled: me.isSuccess,
    staleTime: 0,
    gcTime: 0,
    retry: false,
    refetchOnWindowFocus: true,
  });
}

async function securedPost<T>(path: string, body: unknown): Promise<T> {
  await ensureCsrfCookie();
  return apiRequest<T>(path, { method: "POST", body });
}

export const enrollRecoveryEmail = (email: string, currentPassword: string) =>
  securedPost<RecoveryEmailStatus>(EMAIL_PATH, {
    email: normalizeRecoveryEmail(email),
    current_password: currentPassword,
  });
export const resendRecoveryEmail = () =>
  securedPost<RecoveryEmailStatus>(`${EMAIL_PATH}resend/`, {});
export const checkRecoveryEmail = (token: string) =>
  securedPost<{ status: "VALID" }>(`${EMAIL_PATH}verify/check/`, { token });
export const verifyRecoveryEmail = (token: string) =>
  securedPost<RecoveryEmailStatus>(`${EMAIL_PATH}verify/`, { token });
export const requestParentPasswordRecovery = (mobile: string) =>
  securedPost<{ message: string }>(RESET_PATH, { mobile });
export const checkParentPasswordRecovery = (token: string) =>
  securedPost<{ status: "VALID" }>(`${RESET_PATH}check/`, { token });
export const completeParentPasswordRecovery = (
  token: string,
  newPassword: string,
  confirmPassword: string,
) => securedPost<{ message: string }>(`${RESET_PATH}complete/`, {
  token,
  new_password: newPassword,
  confirm_password: confirmPassword,
});

/** The secret remains in component memory; checking a link never consumes it. */
export function useRecoveryFragment(): string {
  const [token] = useState(() =>
    new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "",
  );
  useEffect(() => {
    if (window.location.hash) {
      window.history.replaceState(
        window.history.state,
        "",
        `${window.location.pathname}${window.location.search}`,
      );
    }
    const previous = document.querySelector<HTMLMetaElement>('meta[name="referrer"]');
    const policy = previous ?? document.createElement("meta");
    const original = policy.content;
    policy.name = "referrer";
    policy.content = "no-referrer";
    if (!previous) document.head.append(policy);
    return () => {
      if (previous) policy.content = original;
      else policy.remove();
    };
  }, []);
  return token;
}

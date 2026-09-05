const QR_RETURN_PATH = /^\/qr\/[A-Za-z0-9_-]{1,64}$/;

/**
 * لا نقبل وجهة عودة عامة حتى لا تتحول صفحة الدخول إلى open redirect.
 * المسار الوحيد المطلوب حاليًا هو رابط QR داخلي محدود الطول والمحارف.
 */
export function safeReturnTo(value: string | null): string | null {
  return value !== null && QR_RETURN_PATH.test(value) ? value : null;
}

export function withReturnTo(destination: string, returnTo: string | null): string {
  const safe = safeReturnTo(returnTo);
  return safe ? `${destination}?returnTo=${encodeURIComponent(safe)}` : destination;
}

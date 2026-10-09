const QR_RETURN_PATH = /^\/qr\/[A-Za-z0-9_-]{1,64}$/;
const PARENT_RETURN_PATH = /^\/parent(?:\/register\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?$/i;

/**
 * لا نقبل وجهة عودة عامة حتى لا تتحول صفحة الدخول إلى open redirect.
 * نسمح برابط QR محدود أو تسجيل المدرسة بمعرف UUID؛ رمز التفعيل لا يدخل وجهة العودة.
 */
export function safeReturnTo(value: string | null): string | null {
  return value !== null && (QR_RETURN_PATH.test(value) || PARENT_RETURN_PATH.test(value)) ? value : null;
}

export function withReturnTo(destination: string, returnTo: string | null): string {
  const safe = safeReturnTo(returnTo);
  return safe ? `${destination}?returnTo=${encodeURIComponent(safe)}` : destination;
}

/** أمر docker compose الذي تخاطبه اختبارات E2E.
 *
 *  ‏E2E_COMPOSE_PROJECT يوجه أوامر البذر إلى حزمة الشجرة الحالية بدل الحزمة
 *  الافتراضية — بدونه يبذر تشغيل شجرة موازية داخل قاعدة شجرة أخرى.
 */
export const COMPOSE = process.env.E2E_COMPOSE_PROJECT
  ? `docker compose -p ${process.env.E2E_COMPOSE_PROJECT}`
  : "docker compose";

/** عنوان الواجهة والخلفية لهذه الشجرة — الجسر يتصل بالخلفية مباشرة لا عبر Proxy. */
export const FRONTEND_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";
export const BACKEND_URL = process.env.E2E_BACKEND_URL ?? "http://localhost:8000";

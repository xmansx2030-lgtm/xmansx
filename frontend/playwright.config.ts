import { defineConfig, devices } from "@playwright/test";

/** E2E smoke — يتطلب backend يعمل على :8000 (docker compose up backend).
 *
 *  ‏E2E_BASE_URL يوجه التشغيل إلى واجهة شجرة عمل أخرى (تطوير مراحل متوازٍ):
 *  ‏docker compose -p <project> يخدم نفس الكود على منفذ مختلف.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  // الملفات تتشارك مدارس الـ seed وقيود «عملية واحدة جارية لكل مدرسة» — تسلسل كامل
  workers: 1,
  timeout: 60_000,
  // خادم التطوير (Vite) قد يعيد تجميع الاعتماديات فيصفّر أول تحميل صفحة بعد تغير
  // شجرة المصادر؛ محاولة واحدة إضافية تغطي ذلك، وأي إخفاق حقيقي يفشل مرتين.
  retries: 1,
  reporter: [["list"]],
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev",
    url: baseURL,
    reuseExistingServer: true,
    timeout: 60_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});

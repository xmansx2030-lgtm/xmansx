import { defineConfig, devices } from "@playwright/test";

/** E2E smoke — يتطلب backend يعمل على :8000 (docker compose up backend). */
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  // الملفات تتشارك مدارس الـ seed وقيود «عملية واحدة جارية لكل مدرسة» — تسلسل كامل
  workers: 1,
  timeout: 60_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 60_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});

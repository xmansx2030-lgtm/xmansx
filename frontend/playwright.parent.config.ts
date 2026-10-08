import { defineConfig, devices } from "@playwright/test";
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:5173";
const serverAddress = new URL(baseURL);
if (!["localhost", "127.0.0.1", "[::1]"].includes(serverAddress.hostname)) {
  throw new Error("Parent E2E requires an isolated localhost origin.");
}
const preview = process.env.PARENT_E2E_PREVIEW === "1";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "parent-portal.spec.ts",
  workers: 1,
  timeout: 90_000,
  reporter: [["list"]],
  use: { baseURL, trace: "retain-on-failure", timezoneId: "Asia/Riyadh" },
  webServer: {
    command: `npm run ${preview ? "preview" : "dev"} -- --host ${serverAddress.hostname} --port ${serverAddress.port || "5173"} --strictPort`,
    url: baseURL,
    reuseExistingServer: true,
    timeout: 60_000,
  },
  projects: [
    { name: "chromium-parent", use: { ...devices["Desktop Chrome"] } },
  ],
});

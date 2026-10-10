import { defineConfig } from "@playwright/test";

const baseURL = process.env.SEO_BASE_URL ?? "http://127.0.0.1:18090";
if (!["localhost", "127.0.0.1", "[::1]"].includes(new URL(baseURL).hostname)) {
  throw new Error("SEO acceptance tests must use an isolated local frontend");
}
export default defineConfig({
  testDir: "./seo-tests", workers: 1, timeout: 45_000,
  use: { baseURL, browserName: "chromium", timezoneId: "Asia/Riyadh", trace: "retain-on-failure" },
  reporter: "list",
});

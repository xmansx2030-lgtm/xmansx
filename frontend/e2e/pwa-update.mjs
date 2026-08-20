import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(frontendRoot, "..");
const project = process.env.E2E_COMPOSE_PROJECT;
const baseURL = process.env.E2E_BASE_URL;
const password = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";
const npmCli = process.env.npm_execpath;

if (!project || !baseURL || !npmCli) {
  throw new Error("E2E_COMPOSE_PROJECT, E2E_BASE_URL, and npm_execpath are required");
}

function buildAndPublish(version) {
  execFileSync(process.execPath, [npmCli, "run", "build"], {
    cwd: frontendRoot,
    env: { ...process.env, VITE_APP_VERSION: version },
    stdio: "inherit",
  });
  execFileSync(
    "docker",
    ["compose", "-p", project, "cp", "frontend/dist/.", "frontend:/usr/share/nginx/html"],
    { cwd: repoRoot, stdio: "inherit" },
  );
}

buildAndPublish("phase17-v1");

const browser = await chromium.launch();
const context = await browser.newContext({ baseURL });
const page = await context.newPage();

try {
  await page.goto("/login");
  await page.evaluate(async () => navigator.serviceWorker.ready);
  await page.reload();
  await page.getByLabel("رقم الجوال").fill("0550000016");
  await page.getByLabel("كلمة المرور", { exact: true }).fill(password);
  await page.getByRole("button", { name: "تسجيل الدخول" }).click();
  await page.waitForURL("**/platform");
  if ((await page.locator("html").getAttribute("data-app-version")) !== "phase17-v1") {
    throw new Error("Phase 17 update gate did not load v1");
  }

  buildAndPublish("phase17-v2");
  await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    await registration.update();
  });
  await page.getByText("يتوفر تحديث جديد للمنصة.").waitFor({ timeout: 30_000 });
  await page.getByRole("button", { name: "تحديث الآن" }).click();
  await page.waitForFunction(
    () => document.documentElement.dataset.appVersion === "phase17-v2",
    undefined,
    { timeout: 30_000 },
  );
  await page.getByRole("heading", { name: "Platform Admin" }).waitFor();
  console.log("PWA update flow: phase17-v1 -> phase17-v2, session preserved");
} finally {
  await context.close();
  await browser.close();
}

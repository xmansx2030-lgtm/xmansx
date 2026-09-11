import { chromium } from "@playwright/test";
import { mkdtemp, mkdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const baseURL = process.env.PWA_BASE_URL ?? "http://127.0.0.1:4173";
const profile = await mkdtemp(resolve(tmpdir(), "xmansx-pwa-standalone-"));
const artifactDir = resolve(frontendRoot, "test-results", "pwa-standalone");
await mkdir(artifactDir, { recursive: true });

const context = await chromium.launchPersistentContext(profile, {
  headless: process.env.PWA_HEADLESS === "1",
  viewport: { width: 390, height: 844 },
  args: [
    `--app=${baseURL}/login`,
    "--no-first-run",
    "--no-default-browser-check",
  ],
});

try {
  const page = context.pages()[0] ?? await context.newPage();
  await page.goto(`${baseURL}/login`, { waitUntil: "domcontentloaded" });
  await page.evaluate(async () => navigator.serviceWorker.ready);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
  await page.waitForTimeout(1_200);

  const result = await page.evaluate(async () => {
    const manifestLink = document.querySelector('link[rel="manifest"]');
    if (!(manifestLink instanceof HTMLLinkElement)) throw new Error("Manifest link is missing");
    const manifest = await fetch(manifestLink.href).then((response) => response.json());
    const maskable = manifest.icons?.find((icon) => String(icon.purpose).includes("maskable"));
    const iconStatus = maskable
      ? await fetch(new URL(maskable.src, location.href)).then((response) => response.status)
      : 0;
    return {
      displayMode: window.matchMedia("(display-mode: standalone)").matches,
      serviceWorkerControlled: Boolean(navigator.serviceWorker.controller),
      manifest: {
        display: manifest.display,
        dir: manifest.dir,
        lang: manifest.lang,
        themeColor: manifest.theme_color,
        maskable: Boolean(maskable),
      },
      iconStatus,
      direction: document.documentElement.dir,
      viewport: document.documentElement.clientWidth,
      content: document.documentElement.scrollWidth,
      installDialogVisible: Boolean(document.querySelector('[role="dialog"]')),
      themeMeta: document.querySelector('meta[name="theme-color"]')?.getAttribute("content"),
    };
  });

  if (!result.displayMode) throw new Error("Chromium app window did not expose standalone display mode");
  if (!result.serviceWorkerControlled) throw new Error("Service worker did not control the standalone app");
  if (result.manifest.display !== "standalone" || result.manifest.dir !== "rtl" || result.manifest.lang !== "ar") {
    throw new Error(`Invalid standalone manifest: ${JSON.stringify(result.manifest)}`);
  }
  if (!result.manifest.maskable || result.iconStatus !== 200) throw new Error("Maskable PWA icon is unavailable");
  if (result.direction !== "rtl") throw new Error("Standalone document is not RTL");
  if (result.content > result.viewport + 1) throw new Error(`Standalone overflow: ${result.content}/${result.viewport}`);
  if (result.installDialogVisible) throw new Error("Install prompt appeared inside standalone mode");
  if (result.themeMeta !== "#0f766e" || result.manifest.themeColor !== "#0f766e") {
    throw new Error("Standalone theme colors are inconsistent");
  }

  await page.screenshot({ path: resolve(artifactDir, "login-390x844.png"), fullPage: false });
  console.log(JSON.stringify(result, null, 2));
} finally {
  await context.close();
  await rm(profile, { recursive: true, force: true });
}

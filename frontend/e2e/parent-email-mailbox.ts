/** Private synthetic mailbox reader. Never expose it as an application API. */
import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { promisify } from "node:util";

import { FRONTEND_URL } from "./compose";

const execFileAsync = promisify(execFile);
export const RECOVERY_MESSAGE = "إذا كان الحساب مسجلاً وله بريد إلكتروني موثق، فسيتم إرسال رابط استعادة كلمة المرور إليه.";
export const LINK_UNAVAILABLE_MESSAGE = "رابط الاسترداد غير صالح أو انتهت صلاحيته. اطلب رابطاً جديداً.";

export const emailForMobile = (mobile: string) =>
  `guardian-${mobile.replace(/\D/g, "")}@parent-e2e.invalid`;

export async function securePost(context: APIRequestContext, path: string, data: unknown) {
  const csrf = (await context.storageState()).cookies.find((cookie) => cookie.name === "csrftoken")?.value ?? "";
  return context.post(`/api/v1${path}`, {
    data, headers: { "X-CSRFToken": csrf, Origin: new URL(FRONTEND_URL).origin },
  });
}

/** The stdout is captured in memory; failures must not print a secret link. */
async function readSyntheticLink(recipient: string, purpose: string): Promise<string> {
  const project = process.env.COMPOSE_PROJECT_NAME;
  if (
    process.env.PARENT_E2E_SYNTHETIC_STAGING !== "1" ||
    process.env.PARENT_VERIFICATION_LOCAL_ONLY !== "1" ||
    FRONTEND_URL !== "https://localhost:8445" ||
    !project ||
    !["xmansx-parent-release-clean-synthetic-staging", "xmansx-parent-email-activation-synthetic-staging"].includes(project ?? "") ||
    !recipient.toLowerCase().endsWith(".invalid") ||
    !["RECOVERY_EMAIL_VERIFICATION", "PASSWORD_RESET", "PARENT_ACCOUNT_ACTIVATION"].includes(purpose)
  ) throw new Error("Recovery browser tests require the isolated private synthetic mailbox.");
  const environment = resolve("..", "artifacts", "parent-staging", ".env");
  if (!existsSync(environment)) throw new Error("Synthetic staging materials are required.");
  const script = [
    "import json, os, pathlib, stat, sys, uuid",
    "assert os.environ.get('DJANGO_SETTINGS_MODULE') == 'config.settings.parent_staging'",
    "assert os.environ.get('PARENT_STAGING_LOCAL_ONLY') == '1' and os.geteuid() == 65534",
    "assert os.environ.get('PARENT_RECOVERY_EMAIL_ADAPTER') == 'synthetic-file'",
    "assert not os.environ.get('RESEND_API_KEY')",
    "root = pathlib.Path(os.environ['PARENT_RECOVERY_SYNTHETIC_EMAIL_ROOT'])",
    "assert str(root) == '/var/lib/xmansx-parent-staging/email-outbox'",
    "assert not root.is_symlink() and root.resolve() == root",
    "assert stat.S_IMODE(root.stat().st_mode) == 0o700",
    "recipient, purpose = sys.argv[1:]",
    "assert recipient.endswith('.invalid') and purpose in {'RECOVERY_EMAIL_VERIFICATION','PASSWORD_RESET','PARENT_ACCOUNT_ACTIVATION'}",
    "matched = []",
    "for path in root.glob('*.json'):",
    "    assert not path.is_symlink() and str(uuid.UUID(path.stem)) == path.stem",
    "    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and path.stat().st_size <= 16384",
    "    try:",
    "        data = json.loads(path.read_text(encoding='utf-8'))",
    "    except (FileNotFoundError, json.JSONDecodeError):",
    "        continue",
    "    if data.get('to') == recipient and data.get('purpose') == purpose:",
    "        matched.append((path.stat().st_mtime_ns, data['link']))",
    "print(max(matched)[1] if matched else '', end='')",
  ].join("\n");
  try {
    const { stdout } = await execFileAsync("docker", [
      "compose", "--env-file", environment,
      "-f", resolve("..", "docker-compose.parent-verification.yml"),
      "-f", resolve("..", "docker-compose.parent-release-verification.yml"),
      "-f", resolve("..", "docker-compose.parent-staging.yml"),
      "-p", project, "exec", "-T", "staging-worker", "python", "-c", script, recipient, purpose,
    ], { cwd: resolve(".."), timeout: 20_000, encoding: "utf8", maxBuffer: 4096 });
    const link = stdout.trim();
    if (link) {
      const parsed = new URL(link);
      const path = purpose === "PARENT_ACCOUNT_ACTIVATION" ? "/parent/activate" : purpose === "PASSWORD_RESET" ? "/reset-password" : "/parent/verify-email";
      if (
        parsed.origin !== "https://localhost:8445" || parsed.pathname !== path ||
        parsed.search || !/^#token=[A-Za-z0-9_-]{32,128}$/.test(parsed.hash)
      ) throw new Error("Invalid private synthetic link.");
    }
    return link;
  } catch {
    // execFile errors include stdout/stderr. Do not forward those error objects.
    throw new Error("Unable to read the isolated synthetic recovery mailbox.");
  }
}

export async function syntheticRecoveryLink(recipient: string, purpose: string): Promise<string> {
  let link = "";
  await expect.poll(async () => {
    link = await readSyntheticLink(recipient, purpose);
    return Boolean(link);
  }, { timeout: 30_000, intervals: [500, 1000, 2000] }).toBe(true);
  return link;
}

export async function completeRecoveryEmail(
  page: Page, mobile: string, password: string, email = emailForMobile(mobile),
) {
  // Await the activation response/navigation before issuing an owner request.
  await expect(page).toHaveURL(/\/parent(?:\/recovery-email)?$/);
  const response = await page.request.get("/api/v1/parent/recovery-email/");
  expect(response.status()).toBe(200);
  const status = await response.json() as { verified: boolean; pending_email_masked: string };
  if (status.verified) return;
  expect((await page.request.get("/api/v1/parent/children/")).status()).toBe(403);
  await page.goto("/parent/recovery-email");
  await expect(page.getByText("بانتظار توثيق بريد الاسترداد", { exact: true })).toBeVisible();
  if (!status.pending_email_masked) {
    await page.getByLabel("البريد الإلكتروني", { exact: true }).fill(email);
    await page.getByLabel("كلمة المرور الحالية", { exact: true }).fill(password);
    await page.getByRole("button", { name: "إرسال رابط توثيق البريد", exact: true }).click();
    await expect(page.getByRole("button", { name: "إعادة إرسال رابط التحقق", exact: true })).toBeVisible();
  }
  const link = await syntheticRecoveryLink(email, "RECOVERY_EMAIL_VERIFICATION");
  const committed: string[] = [];
  const observe = (request: import("@playwright/test").Request) => {
    if (new URL(request.url()).pathname === "/api/v1/parent/recovery-email/verify/" && request.method() === "POST") committed.push("verify");
  };
  page.on("request", observe);
  try {
    await page.goto(link);
    await expect(page.getByRole("button", { name: "توثيق البريد الإلكتروني", exact: true })).toBeVisible();
    expect(committed).toEqual([]);
    expect(new URL(page.url()).hash).toBe("");
    expect((await (await page.request.get("/api/v1/parent/recovery-email/")).json()).verified).toBe(false);
    expect((await page.request.get("/api/v1/parent/children/")).status()).toBe(403);
    await page.getByRole("button", { name: "توثيق البريد الإلكتروني", exact: true }).click();
    await expect(page.getByText("تم توثيق بريد الاسترداد", { exact: true })).toBeVisible();
    expect(committed).toEqual(["verify"]);
    await page.getByRole("link", { name: "الانتقال إلى أبنائي", exact: true }).click();
    await expect(page.getByTestId("parent-shell")).toBeVisible();
  } finally { page.off("request", observe); }
}

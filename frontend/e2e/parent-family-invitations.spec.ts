import { expect, test } from "@playwright/test";
import { execFile } from "node:child_process";
import { readFileSync } from "node:fs";
import { promisify } from "node:util";
import { FRONTEND_URL } from "./compose";
import { completeRecoveryEmail, securePost } from "./parent-email-mailbox";

test.use({ trace: "off" }); // Bearers stay out of diagnostic browser traces.
const run = promisify(execFile);
const fixture = JSON.parse(readFileSync(process.env.PARENT_E2E_FIXTURE!, "utf-8")) as {
  schools: Array<{ id: number; staff_mobile: string; acceptance_staff: { VICE_PRINCIPAL: { mobile: string } } }>;
  family_invitations: Array<{ viewport: string; name: string; mobile: string; email: string; children: Array<{ id: number; name: string }> }>;
};
const password = process.env.E2E_SEED_PASSWORD!;
if (!password || fixture.schools.length !== 3 || !fixture.family_invitations ||
  process.env.COMPOSE_PROJECT_NAME !== "xmansx-parent-email-activation-synthetic-staging" ||
  process.env.PARENT_VERIFICATION_LOCAL_ONLY !== "1" || FRONTEND_URL !== "https://localhost:8445") {
  throw new Error("Family browser acceptance requires the independent synthetic TLS stack.");
}

async function privateSmsLink(id: string): Promise<string> {
  if (!/^[a-f0-9-]{36}$/.test(id)) throw new Error("Invalid synthetic invitation ID.");
  const script = [
    "import json,os,pathlib,stat,sys,uuid",
    "assert os.geteuid()==65534 and os.environ.get('PARENT_STAGING_LOCAL_ONLY')=='1'",
    "assert os.environ.get('PARENT_FAMILY_INVITATION_SMS_ADAPTER')=='synthetic-file'",
    "root=pathlib.Path('/var/lib/xmansx-parent-staging/email-outbox/family-invitations')",
    "assert not root.is_symlink() and stat.S_IMODE(root.stat().st_mode)==0o700",
    "invitation=str(uuid.UUID(sys.argv[1])); path=root/(invitation+'.json')",
    "assert not path.is_symlink() and stat.S_IMODE(path.stat().st_mode)==0o600",
    "assert path.stat().st_size<4096",
    "data=json.loads(path.read_text(encoding='utf-8'))",
    "assert data['id']==invitation and data['purpose']=='FAMILY_INVITATION_SMS'",
    "assert len(list(root.glob(invitation+'.json')))==1",
    "print(data['link'],end='')",
  ].join("\n");
  try {
    const { stdout } = await run("docker", ["exec", "xmansx-parent-email-activation-synthetic-staging-staging-app-1", "python", "-c", script, id], { timeout: 20_000, maxBuffer: 4096 });
    const link = stdout.trim(); const parsed = new URL(link);
    if (parsed.origin !== FRONTEND_URL || parsed.pathname !== "/parent/invitation" || parsed.search || !/^#token=[A-Za-z0-9_-]{40,128}$/.test(parsed.hash)) throw new Error();
    return link;
  } catch { throw new Error("Private synthetic SMS was unavailable; secret output suppressed."); }
}

for (const viewport of [
  { name: "desktop", width: 1366, height: 900 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
]) {
  test(`review one family SMS, email gate and staff distinction on ${viewport.name}`, async ({ page, playwright }) => {
    await page.setViewportSize(viewport);
    const school = fixture.schools[0]!;
    const family = fixture.family_invitations.find((row) => row.viewport === viewport.name)!;
    const manager = await playwright.request.newContext({ baseURL: FRONTEND_URL, ignoreHTTPSErrors: false });
    const vice = await playwright.request.newContext({ baseURL: FRONTEND_URL, ignoreHTTPSErrors: false });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    async function overflow() {
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    }
    try {
      for (const [context, mobile] of [[manager, school.staff_mobile], [vice, school.acceptance_staff.VICE_PRINCIPAL.mobile]] as const) {
        expect((await context.get("/api/v1/auth/csrf/")).status()).toBe(200);
        expect((await securePost(context, "/auth/login/", { mobile, password })).status()).toBe(200);
      }
      const sender = viewport.name === "tablet" ? vice : manager;
      await page.context().addCookies((await sender.storageState()).cookies);
      await page.goto("/parent-management?tab=families");
      await expect(page.getByRole("heading", { name: "إدارة أولياء الأمور", exact: true })).toBeVisible({ timeout: 20_000 });
      const card = page.getByRole("article").filter({ has: page.getByRole("heading", { name: family.name, exact: true }) });
      await expect(card.getByText("لم تُرسل دعوة", { exact: true })).toBeVisible();
      for (const child of family.children) await expect(card.getByText(child.name, { exact: true })).toBeVisible();
      await card.getByRole("button", { name: `اعتماد وإرسال دعوة ${family.name}`, exact: true }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByRole("button", { name: "اعتماد وإرسال 1 دعوة", exact: true })).toBeDisabled();
      await dialog.getByLabel("توثيق التحقق من صفة ولي الأمر والرقم والأبناء").fill("تحقق صناعي مستقل من صفة ولي الأمر وجميع الأبناء الثلاثة والرقم");
      await dialog.getByLabel(/أؤكد أنني تحققت/).check();
      await overflow();
      await page.screenshot({ path: `../artifacts/parent-staging/family-invitations-${viewport.name}-review.png`, fullPage: false });
      const saved = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/staff/parents/families/" && response.request().method() === "POST");
      await dialog.getByRole("button", { name: "اعتماد وإرسال 1 دعوة", exact: true }).click();
      const response = await saved; expect(response.status()).toBe(201);
      const invitation = (await response.json()).invitations[0] as { id: string; delivery_status: string };
      expect(invitation.delivery_status).toBe("SENT");
      await expect(card.getByText("دعوة مقبولة لدى مزود SMS", { exact: true })).toBeVisible();
      await card.scrollIntoViewIfNeeded(); await overflow();
      await page.screenshot({ path: `../artifacts/parent-staging/family-invitations-${viewport.name}-sent.png`, fullPage: false });
      for (const reviewer of [manager, vice]) {
        const rows = (await (await reviewer.get("/api/v1/staff/parents/families/")).json()).results as Array<{ name: string; invitation: { delivery_status: string; student_ids: number[] } }>;
        const row = rows.find((item) => item.name === family.name)!;
        expect(row.invitation.delivery_status).toBe("SENT");
        expect(row.invitation.student_ids.sort()).toEqual(family.children.map((child) => child.id).sort());
      }
      const link = await privateSmsLink(invitation.id);
      const bearer = new URLSearchParams(new URL(link).hash.slice(1)).get("token")!;
      await page.context().clearCookies();
      await page.goto(link);
      await expect(page.getByRole("heading", { name: "دعوة متابعة الأبناء" })).toBeVisible();
      await expect(page.getByLabel("البريد الإلكتروني", { exact: true })).toBeVisible();
      expect(new URL(page.url()).hash).toBe("");
      expect(await page.getByLabel(/معرف الطالب/).count()).toBe(0);
      await page.getByLabel("البريد الإلكتروني", { exact: true }).fill(family.email);
      await page.getByLabel("كلمة المرور الجديدة", { exact: true }).fill(password);
      await page.getByLabel("تأكيد كلمة المرور الجديدة", { exact: true }).fill(password);
      await overflow();
      await page.screenshot({ path: `../artifacts/parent-staging/family-invitations-${viewport.name}-parent.png`, fullPage: true });
      await page.getByRole("button", { name: "تفعيل الربط والمتابعة", exact: true }).click();
      await completeRecoveryEmail(page, family.mobile, password, family.email);
      for (const child of family.children) await expect(page.getByText(child.name, { exact: true })).toBeVisible();
      expect((await securePost(page.request, "/parent/family-invitation/activate/", { token: bearer, email: family.email })).status()).toBe(409);
      for (const reviewer of [manager, vice]) {
        const rows = (await (await reviewer.get("/api/v1/staff/parents/families/")).json()).results as Array<{ name: string; invitation: { lifecycle: string } }>;
        expect(rows.find((item) => item.name === family.name)?.invitation.lifecycle).toBe("ACTIVATED");
      }
      await page.context().clearCookies(); await page.context().addCookies((await vice.storageState()).cookies);
      await page.goto("/parent-management?tab=families");
      await expect(card.getByText("تم تفعيل الربط", { exact: true })).toBeVisible();
      await expect(card.getByRole("button", { name: `الربط مكتمل ${family.name}` })).toBeDisabled();
      await overflow(); expect(errors).toEqual([]);
    } finally { await manager.dispose(); await vice.dispose(); }
  });
}

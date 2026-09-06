import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  expect,
  test,
  type APIRequest,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

import { FRONTEND_URL } from "./compose";

const PASSWORD = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";
const PLATFORM_MOBILE = "0550000016";
const FIXTURES = resolve(dirname(fileURLToPath(import.meta.url)), "fixtures");

interface ApiErrorBody {
  code: string;
  message: string;
}

async function csrf(ctx: APIRequestContext): Promise<string> {
  await ctx.get("/api/v1/auth/csrf/");
  return (await ctx.storageState()).cookies.find((cookie) => cookie.name === "csrftoken")?.value ?? "";
}

async function login(
  requestFactory: APIRequest,
  mobile: string,
  password: string,
): Promise<APIRequestContext> {
  const ctx = await requestFactory.newContext({ baseURL: FRONTEND_URL });
  const response = await ctx.post("/api/v1/auth/login/", {
    data: { mobile, password },
    headers: { "X-CSRFToken": await csrf(ctx) },
  });
  expect(response.status()).toBe(200);
  return ctx;
}

async function post(ctx: APIRequestContext, path: string, data: unknown) {
  return ctx.post(`/api/v1${path}`, {
    data,
    headers: { "X-CSRFToken": await csrf(ctx) },
  });
}

async function patch(ctx: APIRequestContext, path: string, data: unknown) {
  return ctx.patch(`/api/v1${path}`, {
    data,
    headers: { "X-CSRFToken": await csrf(ctx) },
  });
}

function djangoShell(code: string): void {
  const project = process.env.E2E_COMPOSE_PROJECT;
  const args = ["compose"];
  if (project) args.push("-p", project);
  args.push("exec", "-T", "backend", "python", "manage.py", "shell", "-c", code);
  execFileSync("docker", args, {
    cwd: resolve(FIXTURES, "..", "..", ".."),
    stdio: "inherit",
  });
}

async function useSession(page: Page, ctx: APIRequestContext): Promise<void> {
  await page.context().clearCookies();
  await page.context().addCookies((await ctx.storageState()).cookies);
}

test("Phase 16 SaaS lifecycle, limits, isolation, and recovery", async ({
  page,
  playwright,
}) => {
  test.setTimeout(240_000);
  const unique = String(Date.now()).slice(-7);
  const managerMobile = `057${unique}`;
  const platform = await login(playwright.request, PLATFORM_MOBILE, PASSWORD);

  await useSession(page, platform);
  await page.goto("/platform");
  await expect(page.getByRole("heading", { name: "إدارة المنصة" })).toBeVisible();

  const lowPlanResponse = await post(platform, "/platform/plans/", {
    code: `phase16-low-${unique}`,
    name_ar: `باقة محدودة ${unique}`,
    trial_days_default: 7,
    entitlements: {
      MAX_STUDENTS: 1,
      MAX_STAFF: 10,
      MAX_DEVICES: 1,
      MAX_STORAGE_GB: 1,
      COUNSELING: false,
    },
  });
  expect(lowPlanResponse.status()).toBe(201);
  const lowPlan = (await lowPlanResponse.json()) as { id: number };

  const highPlanResponse = await post(platform, "/platform/plans/", {
    code: `phase16-high-${unique}`,
    name_ar: `باقة موسعة ${unique}`,
    entitlements: {
      MAX_STUDENTS: 500,
      MAX_STAFF: 50,
      MAX_DEVICES: 2,
      MAX_STORAGE_GB: 10,
      COUNSELING: true,
    },
  });
  expect(highPlanResponse.status()).toBe(201);
  const highPlan = (await highPlanResponse.json()) as { id: number };

  const schoolResponse = await post(platform, "/platform/schools/", {
    school_name: `مدرسة Phase 16 ${unique}`,
    school_type: "BOYS",
    manager_name: "مدير Phase 16",
    manager_mobile: managerMobile,
    plan_id: lowPlan.id,
    subscription_mode: "TRIAL",
    trial_days: 7,
  });
  expect(schoolResponse.status()).toBe(201);
  const school = (await schoolResponse.json()) as {
    id: number;
    temporary_password: string;
  };
  expect(school.temporary_password).toBeTruthy();

  djangoShell(`
from datetime import date
from academics.models import AcademicYear, AcademicYearStatus
from schools.models import School
from students.models import Student
school = School.objects.get(id=${school.id})
AcademicYear.objects.create(school=school, name='Phase16 E2E', start_date=date(2026,8,1), end_date=date(2027,6,25), status=AcademicYearStatus.ACTIVE)
Student.objects.create(school=school, national_id_encrypted='phase16-e2e', national_id_lookup_hash='phase16-${unique}', national_id_masked='******0000', student_number='P16-${unique}', full_name='طالب محفوظ Phase 16')
`);

  const manager = await login(
    playwright.request,
    managerMobile,
    school.temporary_password,
  );
  const passwordChange = await post(manager, "/auth/change-initial-password/", {
    current_password: school.temporary_password,
    new_password: `Phase16-${unique}!Safe`,
    confirm_password: `Phase16-${unique}!Safe`,
  });
  expect(passwordChange.status()).toBe(200);

  const detailBeforeResponse = await platform.get(
    `/api/v1/platform/schools/${school.id}/`,
  );
  const detailBefore = await detailBeforeResponse.json();
  expect(detailBefore.usage.students.used).toBe(1);
  expect(detailBefore.temporary_password).toBeUndefined();

  djangoShell(`
from datetime import timedelta
from django.core.management import call_command
from django.utils import timezone
from subscriptions.models import SchoolSubscription
sub = SchoolSubscription.objects.filter(school_id=${school.id}).latest('id')
now = timezone.now()
sub.starts_at = now - timedelta(days=30)
sub.ends_at = now - timedelta(days=1)
sub.trial_started_at = sub.starts_at
sub.trial_ends_at = sub.ends_at
sub.save()
call_command('process_subscription_transitions')
call_command('process_subscription_transitions')
`);

  const expiredState = await manager.get("/api/v1/school/subscription/");
  expect(expiredState.status()).toBe(200);
  expect((await expiredState.json()).subscription.status).toBe("EXPIRED");
  const expiredWrite = await post(manager, "/devices/", {
    name: "جهاز أثناء الانتهاء",
    vendor: "ZKTeco",
    serial_number: `EXPIRED-${unique}`,
  });
  expect(expiredWrite.status()).toBe(403);
  expect(((await expiredWrite.json()) as ApiErrorBody).code).toBe("SUBSCRIPTION_EXPIRED");
  const detailAfterExpiry = await platform.get(
    `/api/v1/platform/schools/${school.id}/`,
  );
  expect((await detailAfterExpiry.json()).usage.students.used).toBe(1);

  const activated = await post(
    platform,
    `/platform/schools/${school.id}/subscription/activate/`,
    { plan_id: lowPlan.id, months: 12 },
  );
  expect(activated.status()).toBe(200);

  const firstDeviceResponse = await post(manager, "/devices/", {
    name: "الجهاز الأول",
    vendor: "ZKTeco",
    serial_number: `DEVICE-1-${unique}`,
  });
  expect(firstDeviceResponse.status()).toBe(201);
  const firstDevice = (await firstDeviceResponse.json()) as { id: number };
  const secondDenied = await post(manager, "/devices/", {
    name: "الجهاز الثاني",
    vendor: "ZKTeco",
    serial_number: `DEVICE-2-${unique}`,
  });
  expect(secondDenied.status()).toBe(409);
  expect(((await secondDenied.json()) as ApiErrorBody).code).toBe("DEVICE_LIMIT_EXCEEDED");

  await useSession(page, manager);
  await page.goto("/subscription");
  await expect(page.getByRole("heading", { name: "اشتراك المدرسة" })).toBeVisible();
  await page.goto("/students/import");
  await page.getByTestId("import-file-input").setInputFiles(resolve(FIXTURES, "noor-1.xlsx"));
  await page.getByRole("button", { name: "رفع الملف" }).click();
  await page.getByRole("button", { name: "بدء التحليل" }).click();
  await expect(page.getByText(/يتجاوز الاستيراد حد الباقة: 9 \/ 1/)).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
  await expect(page.getByText(/تجاوز عدد الطلاب حد الباقة/)).toBeVisible();

  const upgraded = await post(
    platform,
    `/platform/schools/${school.id}/subscription/change-plan/`,
    { plan_id: highPlan.id, reason: "Phase 16 E2E upgrade" },
  );
  expect(upgraded.status()).toBe(200);
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
  await expect(page.getByTestId("import-result")).toContainText("طلاب جدد: 8", {
    timeout: 30_000,
  });

  const secondDeviceResponse = await post(manager, "/devices/", {
    name: "الجهاز الثاني",
    vendor: "ZKTeco",
    serial_number: `DEVICE-2-${unique}`,
  });
  expect(secondDeviceResponse.status()).toBe(201);
  const downgraded = await post(
    platform,
    `/platform/schools/${school.id}/subscription/change-plan/`,
    { plan_id: lowPlan.id, reason: "Phase 16 E2E safe downgrade" },
  );
  expect(downgraded.status()).toBe(200);
  const overLimitResponse = await platform.get(
    `/api/v1/platform/schools/${school.id}/`,
  );
  const overLimit = await overLimitResponse.json();
  expect(overLimit.usage.students.used).toBe(9);
  expect(overLimit.usage.students.over_limit).toBe(true);
  expect(overLimit.usage.devices.used).toBe(2);
  expect(overLimit.usage.devices.over_limit).toBe(true);

  const suspended = await post(
    platform,
    `/platform/schools/${school.id}/subscription/suspend/`,
    { reason: "Phase 16 E2E suspension" },
  );
  expect(suspended.status()).toBe(200);
  const suspendedWrite = await patch(manager, `/devices/${firstDevice.id}/`, {
    name: "محاولة أثناء الإيقاف",
  });
  expect(suspendedWrite.status()).toBe(403);
  expect(((await suspendedWrite.json()) as ApiErrorBody).code).toBe("SCHOOL_SUSPENDED");
  expect((await platform.get(`/api/v1/platform/schools/${school.id}/`)).status()).toBe(200);

  const reactivated = await post(
    platform,
    `/platform/schools/${school.id}/subscription/reactivate/`,
    { reason: "Phase 16 E2E reactivation" },
  );
  expect(reactivated.status()).toBe(200);
  const restoredWrite = await patch(manager, `/devices/${firstDevice.id}/`, {
    name: "عاد للعمل",
  });
  expect(restoredWrite.status()).toBe(200);

  const planEdit = await patch(platform, `/platform/plans/${lowPlan.id}/`, {
    entitlements: { MAX_STUDENTS: 1500 },
  });
  expect(planEdit.status()).toBe(200);
  const existingSnapshot = await platform.get(`/api/v1/platform/schools/${school.id}/`);
  expect((await existingSnapshot.json()).entitlements.MAX_STUDENTS.numeric).toBe(1);

  const secondSchoolResponse = await post(platform, "/platform/schools/", {
    school_name: `مدرسة منتهية ${unique}`,
    school_type: "BOYS",
    manager_name: "المدير نفسه",
    manager_mobile: managerMobile,
    plan_id: lowPlan.id,
    subscription_mode: "ACTIVE",
  });
  expect(secondSchoolResponse.status()).toBe(201);
  const secondSchool = (await secondSchoolResponse.json()) as { id: number };
  const newSnapshot = await platform.get(`/api/v1/platform/schools/${secondSchool.id}/`);
  expect((await newSnapshot.json()).entitlements.MAX_STUDENTS.numeric).toBe(1500);

  djangoShell(`
from datetime import timedelta
from django.core.management import call_command
from django.utils import timezone
from subscriptions.models import SchoolSubscription
sub = SchoolSubscription.objects.filter(school_id=${secondSchool.id}).latest('id')
now = timezone.now()
sub.starts_at = now - timedelta(days=30)
sub.ends_at = now - timedelta(days=1)
sub.save()
call_command('process_subscription_transitions')
`);
  expect(
    (await post(manager, "/session/active-school/", { school_id: secondSchool.id })).status(),
  ).toBe(200);
  expect(
    (await (await manager.get("/api/v1/school/subscription/")).json()).subscription.status,
  ).toBe("EXPIRED");
  expect(
    (await post(manager, "/session/active-school/", { school_id: school.id })).status(),
  ).toBe(200);
  expect(
    (await (await manager.get("/api/v1/school/subscription/")).json()).subscription.status,
  ).toBe("ACTIVE");

  await useSession(page, manager);
  await page.goto("/platform");
  await expect(page.getByRole("heading", { name: "إدارة المنصة" })).not.toBeVisible();
  await expect(page.getByTestId("active-school-name")).toBeVisible();

  await manager.dispose();
  await platform.dispose();
});

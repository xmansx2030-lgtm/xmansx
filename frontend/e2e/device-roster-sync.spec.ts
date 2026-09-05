import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

import { expect, test, type APIRequest, type APIRequestContext } from "@playwright/test";
import { BACKEND_URL, FRONTEND_URL } from "./compose";

const PASSWORD = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";

async function csrf(context: APIRequestContext): Promise<string> {
  return (
    (await context.storageState()).cookies.find((cookie) => cookie.name === "csrftoken")?.value ?? ""
  );
}

async function login(requestFactory: APIRequest): Promise<APIRequestContext> {
  const context = await requestFactory.newContext({ baseURL: FRONTEND_URL });
  await context.get("/api/v1/auth/csrf/");
  const cookies = await context.storageState();
  const csrfToken = cookies.cookies.find((cookie) => cookie.name === "csrftoken")?.value ?? "";
  const response = await context.post("/api/v1/auth/login/", {
    data: { mobile: "0550000002", password: PASSWORD },
    headers: { "X-CSRFToken": csrfToken },
  });
  expect(response.status()).toBe(200);
  const schoolsResponse = await context.get("/api/v1/auth/schools/");
  const schools = (await schoolsResponse.json()) as {
    memberships: { school: { id: number } }[];
  };
  const firstSchool = schools.memberships[0]?.school.id;
  expect(firstSchool).toBeTruthy();
  const activeSchool = await context.post("/api/v1/session/active-school/", {
    data: { school_id: firstSchool },
    headers: { "X-CSRFToken": await csrf(context) },
  });
  expect(activeSchool.status()).toBe(200);
  return context;
}

async function post(context: APIRequestContext, path: string, data: unknown) {
  return context.post(path, {
    data,
    headers: { "X-CSRFToken": await csrf(context) },
  });
}

async function patch(context: APIRequestContext, path: string, data: unknown) {
  return context.patch(path, {
    data,
    headers: { "X-CSRFToken": await csrf(context) },
  });
}

const DEVICE_NAME = "Simulator Roster E2E";
const FIXTURES = resolve(import.meta.dirname, "fixtures");

function meta(): { roster_students: string[] } {
  return JSON.parse(readFileSync(resolve(FIXTURES, "meta.json"), "utf-8")) as {
    roster_students: string[];
  };
}

/** يستورد ملف نور الخاص بهذا الاختبار عبر واجهة الاستيراد (نفس مسار المستخدم). */
async function importRosterFixture(context: APIRequestContext) {
  const upload = await context.post("/api/v1/student-imports/", {
    multipart: {
      file: {
        name: "noor-12.xlsx",
        mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buffer: readFileSync(resolve(FIXTURES, "noor-12.xlsx")),
      },
    },
    headers: { "X-CSRFToken": await csrf(context) },
  });
  expect(upload.status()).toBe(201);
  const job = (await upload.json()) as { id: number };
  const processed = await post(context, `/api/v1/student-imports/${job.id}/process/`, {});
  expect([200, 202]).toContain(processed.status());
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const state = (await (
      await context.get(`/api/v1/student-imports/${job.id}/`)
    ).json()) as { status: string };
    if (state.status === "READY_FOR_REVIEW") break;
    await new Promise((done) => setTimeout(done, 500));
  }
  const committed = await post(context, `/api/v1/student-imports/${job.id}/commit/`, {});
  expect([200, 201]).toContain(committed.status());
}

async function findStudents(context: APIRequestContext, names: string[]) {
  const found: { id: number; full_name: string }[] = [];
  for (const name of names) {
    const response = await context.get(
      `/api/v1/students/search/?search=${encodeURIComponent(name)}`,
    );
    const body = (await response.json()) as { results: { id: number; full_name: string }[] };
    if (body.results.length === 1) found.push(body.results[0]);
  }
  return found;
}

/** الأجهزة لا تُحذف (تحمل تاريخًا)، فبقايا التشغيلات السابقة تبقى نشطة وتُعاد في كل
 *  نبضة جسر مع هويات طلابها — تعطيلها يبقي زمن الاختبار ثابتًا بدل أن ينمو. */
async function deactivateLeftoverDevices(context: APIRequestContext) {
  const response = await context.get("/api/v1/devices/");
  const payload = (await response.json()) as { id: number; name: string; is_active: boolean }[];
  const devices = Array.isArray(payload) ? payload : [];
  for (const device of devices) {
    if (device.name.startsWith(DEVICE_NAME) && device.is_active) {
      await patch(context, `/api/v1/devices/${device.id}/`, { is_active: false });
    }
  }
}

async function runBridge(configPath: string) {
  const root = resolve(import.meta.dirname, "..", "..");
  // ‏E2E_PYTHON: شجرة موازية بلا venv خاص بها تستعير مفسر الشجرة الرئيسية
  const venvPython = resolve(root, "backend", ".venv", "Scripts", "python.exe");
  const python =
    process.env.E2E_PYTHON ?? (existsSync(venvPython) ? venvPython : "python");
  execFileSync(python, ["-m", "bridge_core", "run-once", "--config", configPath], {
    cwd: resolve(root, "bridge"),
    env: { ...process.env, PYTHONPATH: resolve(root, "bridge") },
    stdio: "pipe",
  });
}

test("manager creates a missing Simulator roster user and verifies MATCHED", async ({ playwright }) => {
  // مزامنة السجل تنفذ أمرًا حقيقيًا لكل طالب في المدرسة عبر عمليات جسر متتابعة،
  // فزمنها يتناسب مع حجم السجل ويتجاوز مهلة الاختبار الافتراضية.
  test.setTimeout(240_000);
  const context = await login(playwright.request);
  const temp = mkdtempSync(resolve(tmpdir(), "xmansx-roster-e2e-"));
  const usersFile = resolve(temp, "users.json");
  const queueFile = resolve(temp, "queue.sqlite3");
  writeFileSync(usersFile, "[]", "utf8");

  let deviceId = 0;

  try {
    await deactivateLeftoverDevices(context);
    const deviceResponse = await post(context, "/api/v1/devices/", {
      name: DEVICE_NAME,
      vendor: "SIMULATOR",
      model: "E2E",
    });
    expect(deviceResponse.status()).toBe(201);
    const device = (await deviceResponse.json()) as { id: number };
    deviceId = device.id;

    const bridgeResponse = await post(context, "/api/v1/device-bridges/", {
      name: "Simulator Roster Bridge E2E",
    });
    expect(bridgeResponse.status()).toBe(201);
    const bridge = (await bridgeResponse.json()) as { credential: string };

    // طلاب هذا الاختبار وحده: التخريج أدناه يولّد أمر حذف، وتخريج طالب مشترك
    // يكسر specs أخرى (ظهر على قاعدة نظيفة حين خُرّج طالب التحليلات).
    await importRosterFixture(context);
    const ownNames = meta().roster_students;
    const owned = await findStudents(context, ownNames);
    expect(owned).toHaveLength(2);

    const analyzeResponse = await post(context, `/api/v1/devices/${device.id}/roster-sync/analyze/`, {
      device_id: device.id,
    });
    expect(analyzeResponse.status()).toBe(202);
    const initialJob = (await analyzeResponse.json()) as { id: number };

    const configPath = resolve(temp, "bridge.json");
    writeFileSync(
      configPath,
      JSON.stringify({
        saas_url: BACKEND_URL,
        credential: bridge.credential,
        queue_path: queueFile,
        simulator_users_file: usersFile,
        batch_size: 100,
      }),
      "utf8",
    );

    await runBridge(configPath);
    let jobResponse = await context.get(`/api/v1/device-roster-syncs/${initialJob.id}/`);
    let job = (await jobResponse.json()) as { status: string; create_count: number };
    expect(job.status).toBe("READY_FOR_REVIEW");
    expect(job.create_count).toBeGreaterThan(0);

    const itemsResponse = await context.get(`/api/v1/device-roster-syncs/${initialJob.id}/items/?action=CREATE`);
    const createItems = (await itemsResponse.json()) as {
      student_id: number;
      external_user_id: string;
      safe_after_snapshot: { display_name: string };
    }[];
    expect(createItems.length).toBeGreaterThan(0);
    const ownedIds = new Set(owned.map((student) => student.id));
    const managedStudent = createItems.find((item) => ownedIds.has(item.student_id));
    expect(managedStudent).toBeTruthy();

    const approveResponse = await post(context, `/api/v1/device-roster-syncs/${initialJob.id}/approve/`, {});
    expect(approveResponse.status()).toBe(200);

    for (let attempt = 0; attempt < 20; attempt += 1) {
      await runBridge(configPath);
      const progress = (await (await context.get(`/api/v1/device-roster-syncs/${initialJob.id}/`)).json()) as { status: string };
      if (progress.status === "COMPLETED") break;
    }

    const deviceUsers = JSON.parse(readFileSync(usersFile, "utf8")) as {
      external_user_id: string;
      display_name: string;
    }[];
    expect(deviceUsers.length).toBeGreaterThan(0);

    jobResponse = await context.get(`/api/v1/device-roster-syncs/${initialJob.id}/`);
    job = (await jobResponse.json()) as { status: string; create_count: number };
    expect(job.status).toBe("COMPLETED");

    expect(deviceUsers.some((user) => user.display_name.length > 0)).toBe(true);

    const graduateResponse = await post(
      context,
      `/api/v1/students/${managedStudent!.student_id}/status/`,
      { status: "GRADUATED", exit_date: "2026-08-19", exit_reason: "E2E verification" },
    );
    expect(graduateResponse.status()).toBe(200);

    const deleteAnalyze = await post(context, `/api/v1/devices/${device.id}/roster-sync/analyze/`, {
      device_id: device.id,
    });
    expect(deleteAnalyze.status()).toBe(202);
    const deleteJob = (await deleteAnalyze.json()) as { id: number };
    await runBridge(configPath);
    const deleteItemsResponse = await context.get(
      `/api/v1/device-roster-syncs/${deleteJob.id}/items/?action=DELETE`,
    );
    const deleteItems = (await deleteItemsResponse.json()) as { action: string }[];
    expect(deleteItems.length).toBe(1);
    expect(deleteItems[0].action).toBe("DELETE");
    expect((await post(context, `/api/v1/device-roster-syncs/${deleteJob.id}/approve/`, {})).status()).toBe(200);
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await runBridge(configPath);
      const progress = (await (await context.get(`/api/v1/device-roster-syncs/${deleteJob.id}/`)).json()) as { status: string };
      if (progress.status === "COMPLETED") break;
    }
    const afterDeleteUsers = JSON.parse(readFileSync(usersFile, "utf8")) as {
      external_user_id: string;
      display_name: string;
      status: string;
    }[];
    expect(afterDeleteUsers.some((user) => user.external_user_id === managedStudent!.external_user_id)).toBe(false);
    expect((await context.get(`/api/v1/students/${managedStudent!.student_id}/attendance-profile/`)).status()).toBe(200);

    afterDeleteUsers.push({ external_user_id: "manual-unknown", display_name: "مستخدم يدوي", status: "ACTIVE" });
    writeFileSync(usersFile, JSON.stringify(afterDeleteUsers), "utf8");
    const conflictAnalyze = await post(context, `/api/v1/devices/${device.id}/roster-sync/analyze/`, { device_id: device.id });
    const conflictJob = (await conflictAnalyze.json()) as { id: number };
    await runBridge(configPath);
    const conflictItems = (await (await context.get(`/api/v1/device-roster-syncs/${conflictJob.id}/items/?action=CONFLICT`)).json()) as { action: string; external_user_id: string }[];
    expect(conflictItems.some((item) => item.external_user_id === "manual-unknown")).toBe(true);
    expect((await context.get(`/api/v1/device-roster-syncs/${conflictJob.id}/`)).status()).toBe(200);

    const staleAnalyze = await post(context, `/api/v1/devices/${device.id}/roster-sync/analyze/`, { device_id: device.id });
    const staleJob = (await staleAnalyze.json()) as { id: number };
    await runBridge(configPath);
    const staleStudent = owned.find((student) => student.id !== managedStudent!.student_id);
    expect(staleStudent).toBeTruthy();
    expect((await post(context, `/api/v1/students/${staleStudent!.id}/status/`, { status: "GRADUATED" })).status()).toBe(200);
    const staleApprove = await post(context, `/api/v1/device-roster-syncs/${staleJob.id}/approve/`, {});
    expect(staleApprove.status()).toBe(409);
    const staleState = (await context.get(`/api/v1/device-roster-syncs/${staleJob.id}/`)).json() as Promise<{ status: string }>;
    expect((await staleState).status).toBe("STALE");
  } finally {
    if (deviceId) {
      await patch(context, `/api/v1/devices/${deviceId}/`, { is_active: false });
    }
    await context.dispose();
    rmSync(temp, { recursive: true, force: true });
  }
});

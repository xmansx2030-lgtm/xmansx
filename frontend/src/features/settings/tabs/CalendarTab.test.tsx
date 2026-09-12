import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queryClient } from "@/app/queryClient";
import type { AcademicYear, Semester } from "@/features/settings/api";
import { buildMe, membership } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

interface RecordedRequest {
  pathname: string;
  method: string;
  body: unknown;
}

interface CalendarApiHarness {
  calls: RecordedRequest[];
}

type YearWrite = Pick<AcademicYear, "name" | "start_date" | "end_date"> & {
  activate?: boolean;
};

type SemesterWrite = Pick<Semester, "name" | "sequence" | "start_date" | "end_date"> & {
  activate?: boolean;
};

const YEARS_PATH = "/api/v1/school/academic-years/";

function makeSemester(overrides: Partial<Semester> = {}): Semester {
  return {
    id: 61,
    name: "الفصل الأول",
    sequence: 1,
    start_date: "2026-08-23",
    end_date: "2026-12-31",
    status: "ACTIVE",
    ...overrides,
  };
}

function makeYear(overrides: Partial<AcademicYear> = {}): AcademicYear {
  return {
    id: 51,
    name: "2026/2027",
    start_date: "2026-08-23",
    end_date: "2027-06-25",
    status: "ACTIVE",
    semesters: [],
    ...overrides,
  };
}

function cloneYears(years: AcademicYear[]): AcademicYear[] {
  return JSON.parse(JSON.stringify(years)) as AcademicYear[];
}

function managerMe() {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles: ["SCHOOL_MANAGER"],
    memberships: [membership(1, 10, "ثانوية الأندلس", ["SCHOOL_MANAGER"])],
  });
}

function installCalendarApi(initialYears: AcademicYear[]): CalendarApiHarness {
  const years = cloneYears(initialYears);
  let nextYearId = Math.max(100, ...years.map((year) => year.id)) + 1;
  let nextSemesterId =
    Math.max(200, ...years.flatMap((year) => year.semesters.map((semester) => semester.id))) + 1;
  const calls: RecordedRequest[] = [];

  const response = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json", "X-Request-ID": "calendar-test" },
    });

  const notFound = () =>
    response(
      { code: "NOT_FOUND", message: "المورد المطلوب غير موجود.", details: {} },
      404,
    );

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const pathname = new URL(String(input), "http://localhost").pathname;
      const method = (init?.method ?? "GET").toUpperCase();
      const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
      calls.push({ pathname, method, body });

      if (pathname === "/api/v1/auth/me/" && method === "GET") {
        return response(managerMe());
      }

      if (pathname === YEARS_PATH && method === "GET") {
        return response(cloneYears(years));
      }

      if (pathname === YEARS_PATH && method === "POST") {
        const payload = body as YearWrite;
        if (payload.activate) {
          for (const candidate of years) {
            if (candidate.status === "ACTIVE") candidate.status = "CLOSED";
            for (const semester of candidate.semesters) {
              if (semester.status === "ACTIVE") semester.status = "CLOSED";
            }
          }
        }
        const created: AcademicYear = {
          id: nextYearId,
          name: payload.name,
          start_date: payload.start_date,
          end_date: payload.end_date,
          status: payload.activate ? "ACTIVE" : "UPCOMING",
          semesters: [],
        };
        nextYearId += 1;
        years.push(created);
        return response(created, 201);
      }

      const yearDetail = pathname.match(/^\/api\/v1\/school\/academic-years\/(\d+)\/$/);
      if (yearDetail && method === "PATCH") {
        const year = years.find((candidate) => candidate.id === Number(yearDetail[1]));
        if (!year) return notFound();
        Object.assign(year, body as YearWrite);
        return response(year);
      }

      const yearAction = pathname.match(
        /^\/api\/v1\/school\/academic-years\/(\d+)\/(activate|close|archive)\/$/,
      );
      if (yearAction && method === "POST") {
        const year = years.find((candidate) => candidate.id === Number(yearAction[1]));
        if (!year) return notFound();
        const action = yearAction[2];
        if (action === "activate") {
          for (const candidate of years) {
            if (candidate.status === "ACTIVE") candidate.status = "CLOSED";
            for (const semester of candidate.semesters) {
              if (semester.status === "ACTIVE") semester.status = "CLOSED";
            }
          }
          year.status = "ACTIVE";
        } else {
          year.status = action === "close" ? "CLOSED" : "ARCHIVED";
          if (action === "close") {
            for (const semester of year.semesters) {
              if (semester.status === "ACTIVE") semester.status = "CLOSED";
            }
          }
        }
        return response(year);
      }

      const semesterCreate = pathname.match(
        /^\/api\/v1\/school\/academic-years\/(\d+)\/semesters\/$/,
      );
      if (semesterCreate && method === "POST") {
        const year = years.find((candidate) => candidate.id === Number(semesterCreate[1]));
        if (!year) return notFound();
        const payload = body as SemesterWrite;
        if (payload.activate) {
          for (const candidate of years) {
            for (const semester of candidate.semesters) {
              if (semester.status === "ACTIVE") semester.status = "CLOSED";
            }
          }
        }
        const created: Semester = {
          id: nextSemesterId,
          name: payload.name,
          sequence: payload.sequence,
          start_date: payload.start_date,
          end_date: payload.end_date,
          status: payload.activate ? "ACTIVE" : "UPCOMING",
        };
        nextSemesterId += 1;
        year.semesters.push(created);
        return response(created, 201);
      }

      const semesterDetail = pathname.match(/^\/api\/v1\/school\/semesters\/(\d+)\/$/);
      if (semesterDetail && method === "PATCH") {
        const semester = years
          .flatMap((year) => year.semesters)
          .find((candidate) => candidate.id === Number(semesterDetail[1]));
        if (!semester) return notFound();
        Object.assign(semester, body as SemesterWrite);
        return response(semester);
      }

      const semesterActivate = pathname.match(
        /^\/api\/v1\/school\/semesters\/(\d+)\/activate\/$/,
      );
      if (semesterActivate && method === "POST") {
        const semester = years
          .flatMap((year) => year.semesters)
          .find((candidate) => candidate.id === Number(semesterActivate[1]));
        if (!semester) return notFound();
        for (const candidate of years) {
          for (const current of candidate.semesters) {
            if (current.status === "ACTIVE") current.status = "CLOSED";
          }
        }
        semester.status = "ACTIVE";
        return response(semester);
      }

      return notFound();
    }),
  );

  return { calls };
}

function mutationCalls(api: CalendarApiHarness, pathname: string, method: string) {
  return api.calls.filter((call) => call.pathname === pathname && call.method === method);
}

async function renderCalendar(initialYears: AcademicYear[]) {
  const api = installCalendarApi(initialYears);
  renderApp("/settings?section=calendar");
  await screen.findByTestId("academic-calendar-tab");
  return { api, user: userEvent.setup() };
}

describe("CalendarTab", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("creates and activates the first year and semester atomically in their POST bodies", async () => {
    const { api, user } = await renderCalendar([]);

    await user.click(screen.getByRole("button", { name: "إضافة عام دراسي" }));
    const yearDialog = await screen.findByRole("dialog", { name: "إضافة عام دراسي" });
    const yearForm = within(yearDialog).getByRole("form", { name: "إنشاء عام دراسي" });
    await user.clear(within(yearForm).getByLabelText("اسم العام"));
    await user.type(within(yearForm).getByLabelText("اسم العام"), "2026/2027");
    await user.type(within(yearForm).getByLabelText("بداية العام"), "2026-08-23");
    await user.type(within(yearForm).getByLabelText("نهاية العام"), "2027-06-25");
    await user.click(within(yearForm).getByRole("button", { name: "إنشاء العام وتفعيله" }));

    await waitFor(() => expect(mutationCalls(api, YEARS_PATH, "POST")).toHaveLength(1));
    expect(mutationCalls(api, YEARS_PATH, "POST")[0]?.body).toEqual({
      name: "2026/2027",
      start_date: "2026-08-23",
      end_date: "2027-06-25",
      activate: true,
    });
    expect(api.calls.some((call) => call.pathname.endsWith("/activate/"))).toBe(false);
    expect(await screen.findByRole("status")).toHaveTextContent(
      "تم إنشاء العام «2026/2027» وتفعيله في خطوة واحدة.",
    );

    let yearRegion = await screen.findByRole("region", { name: "2026/2027" });
    expect(within(yearRegion).getByTestId("calendar-status")).toHaveTextContent("نشط الآن");
    await user.click(
      within(yearRegion).getByRole("button", { name: "إضافة فصل إلى العام 2026/2027" }),
    );
    const semesterDialog = await screen.findByRole("dialog", {
      name: "إضافة فصل إلى 2026/2027",
    });
    const semesterForm = within(semesterDialog).getByRole("form", {
      name: "إضافة فصل إلى العام 2026/2027",
    });
    await user.clear(within(semesterForm).getByLabelText("اسم الفصل"));
    await user.type(within(semesterForm).getByLabelText("اسم الفصل"), "الفصل الأول");
    await user.clear(within(semesterForm).getByLabelText("بداية الفصل"));
    await user.type(within(semesterForm).getByLabelText("بداية الفصل"), "2026-08-23");
    await user.type(within(semesterForm).getByLabelText("نهاية الفصل"), "2026-12-31");
    await user.click(
      within(semesterForm).getByRole("button", { name: "إنشاء الفصل وتفعيله" }),
    );

    const semesterPath = "/api/v1/school/academic-years/101/semesters/";
    await waitFor(() => expect(mutationCalls(api, semesterPath, "POST")).toHaveLength(1));
    expect(mutationCalls(api, semesterPath, "POST")[0]?.body).toEqual({
      name: "الفصل الأول",
      sequence: 1,
      start_date: "2026-08-23",
      end_date: "2026-12-31",
      activate: true,
    });
    expect(api.calls.some((call) => call.pathname.endsWith("/activate/"))).toBe(false);

    yearRegion = await screen.findByRole("region", { name: "2026/2027" });
    const semesterItem = within(yearRegion).getByRole("listitem", {
      name: "الفصل الأول — 2026/2027",
    });
    expect(within(semesterItem).getByTestId("calendar-status")).toHaveTextContent("نشط الآن");
  });

  it("creates a future year without activating or replacing the current year", async () => {
    const { api, user } = await renderCalendar([makeYear()]);

    await user.click(screen.getByRole("button", { name: "إضافة عام دراسي" }));
    const dialog = await screen.findByRole("dialog", { name: "إضافة عام دراسي" });
    const form = within(dialog).getByRole("form", { name: "إنشاء عام دراسي" });
    await user.clear(within(form).getByLabelText("اسم العام"));
    await user.type(within(form).getByLabelText("اسم العام"), "2027/2028");
    await user.clear(within(form).getByLabelText("بداية العام"));
    await user.type(within(form).getByLabelText("بداية العام"), "2027-08-22");
    await user.clear(within(form).getByLabelText("نهاية العام"));
    await user.type(within(form).getByLabelText("نهاية العام"), "2028-06-22");
    await user.click(within(form).getByRole("button", { name: "حفظ كعام قادم" }));

    await waitFor(() => expect(mutationCalls(api, YEARS_PATH, "POST")).toHaveLength(1));
    expect(mutationCalls(api, YEARS_PATH, "POST")[0]?.body).toEqual({
      name: "2027/2028",
      start_date: "2027-08-22",
      end_date: "2028-06-22",
      activate: false,
    });
    expect(api.calls.some((call) => call.pathname.endsWith("/activate/"))).toBe(false);

    const activeRegion = await screen.findByRole("region", { name: "2026/2027" });
    const upcomingRegion = await screen.findByRole("region", { name: "2027/2028" });
    expect(within(activeRegion).getByTestId("calendar-status")).toHaveTextContent("نشط الآن");
    expect(within(upcomingRegion).getByTestId("calendar-status")).toHaveTextContent("قادم");
  });

  it("edits the selected year and semester through their semantic regions", async () => {
    const initialYear = makeYear({ semesters: [makeSemester()] });
    const { api, user } = await renderCalendar([initialYear]);
    let yearRegion = await screen.findByRole("region", { name: "2026/2027" });

    await user.click(
      within(yearRegion).getByRole("button", { name: "تعديل العام «2026/2027»" }),
    );
    const yearDialog = await screen.findByRole("dialog", { name: "تعديل العام «2026/2027»" });
    const yearForm = within(yearDialog).getByRole("form", { name: "تعديل العام «2026/2027»" });
    await user.clear(within(yearForm).getByLabelText("اسم العام"));
    await user.type(within(yearForm).getByLabelText("اسم العام"), "عام 2026/2027");
    await user.clear(within(yearForm).getByLabelText("نهاية العام"));
    await user.type(within(yearForm).getByLabelText("نهاية العام"), "2027-06-30");
    await user.click(within(yearForm).getByRole("button", { name: "حفظ تعديلات العام" }));

    const yearPath = "/api/v1/school/academic-years/51/";
    await waitFor(() => expect(mutationCalls(api, yearPath, "PATCH")).toHaveLength(1));
    expect(mutationCalls(api, yearPath, "PATCH")[0]?.body).toEqual({
      name: "عام 2026/2027",
      start_date: "2026-08-23",
      end_date: "2027-06-30",
    });

    yearRegion = await screen.findByRole("region", { name: "عام 2026/2027" });
    await user.click(
      within(yearRegion).getByRole("button", {
        name: "تعديل الفصل «الفصل الأول» ضمن العام «عام 2026/2027»",
      }),
    );
    const semesterDialog = await screen.findByRole("dialog", {
      name: "تعديل الفصل «الفصل الأول»",
    });
    const semesterForm = within(semesterDialog).getByRole("form", {
      name: "تعديل الفصل «الفصل الأول»",
    });
    await user.clear(within(semesterForm).getByLabelText("اسم الفصل"));
    await user.type(within(semesterForm).getByLabelText("اسم الفصل"), "الفصل الدراسي الأول");
    await user.clear(within(semesterForm).getByLabelText("نهاية الفصل"));
    await user.type(within(semesterForm).getByLabelText("نهاية الفصل"), "2027-01-10");
    await user.click(
      within(semesterForm).getByRole("button", { name: "حفظ تعديلات الفصل" }),
    );

    const semesterPath = "/api/v1/school/semesters/61/";
    await waitFor(() => expect(mutationCalls(api, semesterPath, "PATCH")).toHaveLength(1));
    expect(mutationCalls(api, semesterPath, "PATCH")[0]?.body).toEqual({
      name: "الفصل الدراسي الأول",
      sequence: 1,
      start_date: "2026-08-23",
      end_date: "2027-01-10",
    });
    yearRegion = await screen.findByRole("region", { name: "عام 2026/2027" });
    expect(
      within(yearRegion).getByRole("listitem", {
        name: "الفصل الدراسي الأول — عام 2026/2027",
      }),
    ).toBeVisible();
  });

  it("requires confirmation for year and semester activation and year closing", async () => {
    const current = makeYear({ semesters: [makeSemester()] });
    const next = makeYear({
      id: 52,
      name: "2027/2028",
      start_date: "2027-08-22",
      end_date: "2028-06-22",
      status: "UPCOMING",
      semesters: [
        makeSemester({
          id: 62,
          start_date: "2027-08-22",
          end_date: "2027-12-31",
          status: "UPCOMING",
        }),
      ],
    });
    const { api, user } = await renderCalendar([current, next]);
    let nextRegion = await screen.findByRole("region", { name: "2027/2028" });

    await user.click(
      within(nextRegion).getByRole("button", { name: "تفعيل العام «2027/2028»" }),
    );
    let dialog = await screen.findByRole("dialog", { name: "تفعيل العام «2027/2028»" });
    expect(within(dialog).getByText("سيُغلق العام النشط «2026/2027» تلقائيًا.")).toBeVisible();
    const activateYearPath = "/api/v1/school/academic-years/52/activate/";
    expect(mutationCalls(api, activateYearPath, "POST")).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "تأكيد تفعيل العام" }));
    await waitFor(() =>
      expect(mutationCalls(api, activateYearPath, "POST")).toHaveLength(1),
    );

    nextRegion = await screen.findByRole("region", { name: "2027/2028" });
    expect(within(nextRegion).getAllByTestId("calendar-status")[0]).toHaveTextContent("نشط الآن");
    await user.click(
      within(nextRegion).getByRole("button", {
        name: "تفعيل الفصل «الفصل الأول» ضمن العام «2027/2028»",
      }),
    );
    dialog = await screen.findByRole("dialog", { name: "تفعيل الفصل «الفصل الأول»" });
    const activateSemesterPath = "/api/v1/school/semesters/62/activate/";
    expect(mutationCalls(api, activateSemesterPath, "POST")).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "تأكيد تفعيل الفصل" }));
    await waitFor(() =>
      expect(mutationCalls(api, activateSemesterPath, "POST")).toHaveLength(1),
    );

    nextRegion = await screen.findByRole("region", { name: "2027/2028" });
    await user.click(
      within(nextRegion).getByRole("button", { name: "إغلاق العام «2027/2028»" }),
    );
    dialog = await screen.findByRole("dialog", { name: "إنهاء العام «2027/2028»" });
    expect(within(dialog).getByText("سيُغلق أيضًا الفصل النشط «الفصل الأول» في العملية نفسها.")).toBeVisible();
    const closeYearPath = "/api/v1/school/academic-years/52/close/";
    expect(mutationCalls(api, closeYearPath, "POST")).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "تأكيد إنهاء العام" }));
    await waitFor(() => expect(mutationCalls(api, closeYearPath, "POST")).toHaveLength(1));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "تم إغلاق العام «2027/2028» وحفظ سجله.",
    );
  });

  it("rejects shrinking a year around an existing semester before PATCH", async () => {
    const { api, user } = await renderCalendar([
      makeYear({ semesters: [makeSemester({ status: "UPCOMING" })] }),
    ]);
    const yearRegion = await screen.findByRole("region", { name: "2026/2027" });
    await user.click(
      within(yearRegion).getByRole("button", { name: "تعديل العام «2026/2027»" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "تعديل العام «2026/2027»" });
    const form = within(dialog).getByRole("form", { name: "تعديل العام «2026/2027»" });
    await user.clear(within(form).getByLabelText("بداية العام"));
    await user.type(within(form).getByLabelText("بداية العام"), "2026-09-01");
    await user.click(within(form).getByRole("button", { name: "حفظ تعديلات العام" }));

    expect(await within(form).findByRole("alert")).toHaveTextContent(
      "لا يمكن تقليص العام لأن الفصل «الفصل الأول» سيصبح خارج حدوده.",
    );
    expect(mutationCalls(api, "/api/v1/school/academic-years/51/", "PATCH")).toHaveLength(0);
  });

  it("rejects a semester outside its year and overlapping another semester before POST", async () => {
    const { api, user } = await renderCalendar([
      makeYear({ semesters: [makeSemester()] }),
    ]);
    const yearRegion = await screen.findByRole("region", { name: "2026/2027" });
    await user.click(
      within(yearRegion).getByRole("button", { name: "إضافة فصل إلى العام 2026/2027" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "إضافة فصل إلى 2026/2027" });
    const form = within(dialog).getByRole("form", { name: "إضافة فصل إلى العام 2026/2027" });
    const startInput = within(form).getByLabelText("بداية الفصل");
    const endInput = within(form).getByLabelText("نهاية الفصل");
    expect(startInput).toHaveAttribute("min", "2026-08-23");
    expect(endInput).toHaveAttribute("max", "2027-06-25");

    fireEvent.change(startInput, { target: { value: "2026-07-01" } });
    fireEvent.change(endInput, { target: { value: "2026-07-31" } });
    fireEvent.submit(form);
    expect(await within(form).findByRole("alert")).toHaveTextContent(
      "يجب أن تكون مواعيد الفصل ضمن حدود العام 2026/2027.",
    );

    await user.clear(startInput);
    await user.type(startInput, "2026-12-20");
    await user.clear(endInput);
    await user.type(endInput, "2027-01-15");
    await user.click(within(form).getByRole("button", { name: "حفظ الفصل" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent(
      "تتداخل هذه المواعيد مع الفصل «الفصل الأول».",
    );
    expect(
      mutationCalls(api, "/api/v1/school/academic-years/51/semesters/", "POST"),
    ).toHaveLength(0);
  });
});

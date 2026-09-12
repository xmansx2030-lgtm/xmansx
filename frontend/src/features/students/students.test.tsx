import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

function meWithRoles(roles: ("SCHOOL_MANAGER" | "TEACHER" | "VICE_PRINCIPAL")[]) {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles,
    memberships: [membership(1, 10, "ثانوية الأندلس", roles)],
  });
}

const STUDENTS_PAGE = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1, full_name: "أحمد محمد", national_id_masked: "******5678",
      student_number: null, status: "ACTIVE", guardian_name: "",
      grade: { id: 1, name: "الأول الثانوي" }, section: { id: 1, name: "1" },
    },
    {
      id: 2, full_name: "خالد سعد", national_id_masked: "******4321",
      student_number: null, status: "ACTIVE", guardian_name: "",
      grade: { id: 1, name: "الأول الثانوي" }, section: { id: 2, name: "2" },
    },
  ],
};

describe("StudentsPage", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("renders students with masked national ids and pagination info", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/students/": { body: STUDENTS_PAGE },
      "/grades/": { body: [] },
      "/sections/": { body: [] },
    });
    renderApp("/students");
    expect(await screen.findByText("أحمد محمد")).toBeInTheDocument();
    expect(screen.getByText("******5678")).toBeInTheDocument();
    expect(screen.queryByText("1012345678")).not.toBeInTheDocument();
    expect(screen.getByText(/الإجمالي: 2 طالبًا/)).toBeInTheDocument();
    // زر الاستيراد للمدير
    expect(screen.getByRole("button", { name: "استيراد" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "إدخال يدوي" })).toBeInTheDocument();
  });

  it("vice principal sees list without import button", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["VICE_PRINCIPAL"]) },
      "/students/": { body: STUDENTS_PAGE },
      "/grades/": { body: [] },
      "/sections/": { body: [] },
    });
    renderApp("/students");
    expect(await screen.findByText("أحمد محمد")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "استيراد" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "إدخال يدوي" })).not.toBeInTheDocument();
  });

  it("يرشد المدير إلى إضافة البيانات عندما لا يوجد طلاب أصلًا", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/students/": { body: { count: 0, next: null, previous: null, results: [] } },
      "/grades/": { body: [] },
      "/sections/": { body: [] },
    });
    renderApp("/students");

    expect(await screen.findByText("لا يوجد طلاب حتى الآن")).toBeInTheDocument();
    expect(screen.getByText(/ابدأ باستيراد بيانات الطلاب من ملف نور/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "استيراد من نور" })).toHaveAttribute("href", "/students/import");
    expect(screen.getByRole("button", { name: "إضافة يدوية" })).toBeInTheDocument();
    expect(screen.queryByText(/معايير البحث/)).not.toBeInTheDocument();
  });

  it("يفرّق النتائج الفارغة بسبب المرشحات ويتيح مسحها", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/students/": { body: { count: 0, next: null, previous: null, results: [] } },
      "/grades/": { body: [] },
      "/sections/": { body: [] },
    });
    renderApp("/students");
    const user = userEvent.setup();

    const search = await screen.findByLabelText("بحث بالاسم");
    await user.type(search, "اسم غير موجود");
    expect(await screen.findByText("لا توجد نتائج مطابقة")).toBeInTheDocument();
    expect(screen.getByText(/وفق معايير البحث الحالية/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "مسح جميع المرشحات" }));

    expect(search).toHaveValue("");
    expect(await screen.findByText("لا يوجد طلاب حتى الآن")).toBeInTheDocument();
  });

  it("adds a student manually from the directory", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/students/": (init) => init?.method === "POST"
        ? { status: 201, body: { ...STUDENTS_PAGE.results[0], id: 9, full_name: "سالم اليدوي" } }
        : { body: STUDENTS_PAGE },
      "/grades/": { body: [{ id: 1, name: "الأول الثانوي", code: "1" }] },
      "/sections/": { body: [{ id: 1, name: "أ", code: "A", grade: { id: 1, name: "الأول الثانوي" } }] },
    });
    renderApp("/students");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "إدخال يدوي" }));
    await user.type(screen.getByLabelText("اسم الطالب الكامل *"), "سالم اليدوي");
    await user.type(screen.getByLabelText("رقم الهوية أو الإقامة *"), "1098765432");
    await user.selectOptions(screen.getByLabelText("الصف *"), "1");
    await user.selectOptions(screen.getByLabelText("الفصل *"), "1");
    await user.click(screen.getByRole("button", { name: "إضافة الطالب" }));
    expect(await screen.findByText("تمت إضافة الطالب سالم اليدوي بنجاح.")).toBeInTheDocument();
  });

  it("lets the manager correct student data and national id without exposing the old id", async () => {
    let patchBody: Record<string, unknown> | null = null;
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/students/1/": (init) => {
        patchBody = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return { body: { ...STUDENTS_PAGE.results[0], full_name: "أحمد المصحح", national_id_masked: "******5432" } };
      },
      "/students/": { body: STUDENTS_PAGE },
      "/grades/": { body: [{ id: 1, name: "الأول الثانوي", code: "1" }] },
      "/sections/": { body: [{ id: 1, name: "1", code: "A", grade: { id: 1, name: "الأول الثانوي" } }] },
    });
    renderApp("/students");
    const user = userEvent.setup();
    await user.click((await screen.findAllByRole("button", { name: "تعديل البيانات" }))[0]!);
    expect(screen.getByText(/الرقم الحالي:/)).toHaveTextContent("******5678");
    const name = screen.getByLabelText("اسم الطالب الكامل *");
    await user.clear(name);
    await user.type(name, "أحمد المصحح");
    await user.type(screen.getByLabelText("تصحيح رقم الهوية أو الإقامة"), "٢٠٩٨٧٦٥٤٣٢");
    await user.click(screen.getByRole("button", { name: "حفظ التعديلات" }));

    expect(await screen.findByText("تم تحديث بيانات الطالب أحمد المصحح بنجاح.")).toBeInTheDocument();
    expect(patchBody).toMatchObject({
      full_name: "أحمد المصحح",
      national_id: "٢٠٩٨٧٦٥٤٣٢",
      section_id: 1,
    });
  });

  it("shows the precise national id validation message", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/students/1/": {
        status: 400,
        body: {
          code: "VALIDATION_ERROR",
          message: "البيانات المدخلة غير صحيحة.",
          details: { national_id: ["رقم الهوية/الإقامة غير صحيح. يجب أن يكون 10 أرقام ويبدأ بـ 1 أو 2."] },
        },
      },
      "/students/": { body: STUDENTS_PAGE },
      "/grades/": { body: [{ id: 1, name: "الأول الثانوي", code: "1" }] },
      "/sections/": { body: [{ id: 1, name: "1", code: "A", grade: { id: 1, name: "الأول الثانوي" } }] },
    });
    renderApp("/students");
    const user = userEvent.setup();
    await user.click((await screen.findAllByRole("button", { name: "تعديل البيانات" }))[0]!);
    await user.type(screen.getByLabelText("تصحيح رقم الهوية أو الإقامة"), "123");
    await user.click(screen.getByRole("button", { name: "حفظ التعديلات" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("10 أرقام ويبدأ بـ 1 أو 2");
  });

  it("يعيد المعلم من رابط الطلاب إلى مساحة عمله ولا يعرض رابط الدليل", async () => {
    mockApi({ "/auth/me/": { body: meWithRoles(["TEACHER"]) } });
    renderApp("/students");
    await screen.findByTestId("active-school-name");
    expect(screen.queryByRole("link", { name: "الطلاب" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("students-page")).not.toBeInTheDocument();
  });
});

describe("ImportWizard", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  const UPLOADED_JOB = {
    id: 5,
    status: "UPLOADED",
    original_filename: "noor.xlsx",
    header_row: 21,
    import_format: "NOOR_OFFICIAL_MULTI_SHEET",
    source_sheet_count: 40,
    detected_rows: 837,
    headers: ["رقم الهوية", "اسم الطالب", "الصف", "الفصل"],
    column_mapping: {},
    suggested_mapping: { national_id: 0, full_name: 1, grade: 2, section: 3 },
    total_rows: 0, valid_rows: 0, invalid_rows: 0, duplicate_rows: 0,
    summary: {}, error_code: "",
  };

  const READY_JOB = {
    ...UPLOADED_JOB,
    status: "READY_FOR_REVIEW",
    total_rows: 3,
    summary: {
      new: 2, unchanged: 0, updated: 0, section_changed: 1,
      grade_changed: 0, errors: 0, duplicates: 0, missing_from_file: 1,
      will_create_grades: ["الأول الثانوي"],
      will_create_sections: ["الأول الثانوي / 1"],
    },
  };
  const COMPLETED_JOB = {
    ...READY_JOB,
    status: "COMPLETED",
    summary: { ...READY_JOB.summary, created: 2, enrollment_changes: 1, unchanged: 0 },
  };

  it("walks through upload → mapping → preview → confirm → result", async () => {
    let processed = false;
    let committed = false;
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/student-imports/5/process/": () => {
        processed = true;
        return { body: { ...READY_JOB } };
      },
      "/student-imports/5/preview/": {
        body: {
          count: 3, next: null, previous: null,
          results: [
            {
              row_number: 2, status: "NEW",
              data: {
                full_name: "أحمد محمد", grade_name: "الأول الثانوي",
                section_name: "1", national_id_masked: "******5678",
              },
              error_codes: [], error_message: "",
            },
          ],
        },
      },
      "/student-imports/5/commit/": () => {
        committed = true;
        return {
          status: 202,
          body: { ...READY_JOB, status: "IMPORTING" },
        };
      },
      "/student-imports/5/": () => ({
        body: committed ? COMPLETED_JOB : processed ? READY_JOB : UPLOADED_JOB,
      }),
      "/student-imports/": { status: 201, body: UPLOADED_JOB },
    });

    renderApp("/students/import");
    const user = userEvent.setup();

    // 1) الرفع
    const file = new File([new Uint8Array([80, 75, 3, 4])], "noor.xlsx");
    const input = (await screen.findByTestId("import-file-input")) as HTMLInputElement;
    await user.upload(input, file);
    await user.click(screen.getByRole("button", { name: "رفع الملف" }));

    // 2) المطابقة — الاقتراح معبأ مسبقًا
    expect(await screen.findByText("مطابقة الأعمدة")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "تم التعرف على تقرير نور الرسمي بنجاح",
    );
    expect(screen.getByRole("status")).toHaveTextContent("جُمعت 40 ورقة، واكتُشف 837 طالبًا");
    const nidSelect = screen.getByLabelText("عمود رقم الهوية") as HTMLSelectElement;
    expect(nidSelect.value).toBe("0");
    await user.click(screen.getByRole("button", { name: "بدء التحليل" }));

    // 3) المعاينة — الفئات بأعدادها + تنبيه المفقودين
    expect(await screen.findByRole("tab", { name: "جدد (2)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "انتقال فصل (1)" })).toBeInTheDocument();
    expect(screen.getByText(/لن يتغيروا تلقائيًا/)).toBeInTheDocument();
    expect(await screen.findByText("أحمد محمد")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "متابعة إلى التأكيد" }));

    // 4) التأكيد — ملخص التغييرات
    const summary = await screen.findByTestId("confirm-summary");
    expect(summary).toHaveTextContent("سيتم إنشاء 2 طالبًا جديدًا");
    expect(summary).toHaveTextContent("سيتم إنشاء الصفوف: الأول الثانوي");
    await user.click(screen.getByRole("button", { name: "اعتماد الاستيراد" }));

    // 5) النتيجة
    const result = await screen.findByTestId("import-result");
    expect(result).toHaveTextContent("طلاب جدد: 2");
    expect(result).toHaveTextContent("تغييرات فصول: 1");
    expect(
      screen.getByRole("link", { name: "مراجعة الطلاب غير الموجودين" }),
    ).toHaveAttribute("href", "/students/inactive?filter=missing");
    expect(processed && committed).toBe(true);
  });

  it("shows preview row errors with row number and Arabic message", async () => {
    let corrected = false;
    const errorJob = {
      ...READY_JOB,
      summary: { ...READY_JOB.summary, new: 0, errors: 1, missing_from_file: 0 },
    };
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/student-imports/5/process/": { body: errorJob },
      "/student-imports/5/preview/": () => ({
        body: corrected ? { count: 0, next: null, previous: null, results: [] } : {
          count: 1, next: null, previous: null,
          results: [
            {
              row_number: 23, status: "ERROR",
              data: { full_name: "محمد أحمد", grade_name: "الأول الثانوي", section_name: "1" },
              error_codes: ["INVALID_NATIONAL_ID"],
              error_message: "رقم الهوية غير صالح.",
            },
          ],
        },
      }),
      "/student-imports/5/rows/23/": () => {
        corrected = true;
        return {
          body: {
            ...errorJob,
            invalid_rows: 0,
            summary: { ...errorJob.summary, errors: 0, new: 1 },
          },
        };
      },
      "/sections/": { body: [] },
      "/student-imports/5/": () => ({
        body: corrected
          ? { ...errorJob, invalid_rows: 0, summary: { ...errorJob.summary, errors: 0, new: 1 } }
          : errorJob,
      }),
      "/student-imports/": { status: 201, body: UPLOADED_JOB },
    });

    renderApp("/students/import");
    const user = userEvent.setup();
    const file = new File([new Uint8Array([80, 75, 3, 4])], "noor.xlsx");
    await user.upload(
      (await screen.findByTestId("import-file-input")) as HTMLInputElement,
      file,
    );
    await user.click(screen.getByRole("button", { name: "رفع الملف" }));
    await user.click(await screen.findByRole("button", { name: "بدء التحليل" }));

    await waitFor(() => {
      expect(screen.getByText("23")).toBeInTheDocument();
      expect(screen.getByText(/رقم الهوية غير صالح/)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "عالج الحالات أولًا" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "معالجة الصف 23" }));
    await user.type(screen.getByLabelText("رقم الهوية الصحيح"), "1012-345-678");
    await user.click(screen.getByRole("button", { name: "حفظ وإعادة الفحص" }));

    expect(await screen.findByText(/اكتملت المراجعة/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "متابعة إلى التأكيد" })).toBeEnabled();
  });
});

import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

const template = "تنبيه: نرجو متابعة الغياب.";
const messagePreview = {
  date: "2026-08-19",
  page: 1,
  page_size: 25,
  total: 0,
  ready_total: 0,
  candidate_student_ids: [],
  selectable_student_ids: [],
  contact_issues: [],
  message_template: template,
  default_message_template: "«اسم الطالب» غائب بتاريخ «التاريخ».",
  integration: { provider: "DREAMS", sender_name: "المدرسة", is_active: true },
  students: [],
};

describe("absence SMS template editor", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("offers token insertion and a live, substituted sample without saving", async () => {
    mockApi({
      "/auth/me/": {
        body: buildMe({
          active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
          roles: ["SCHOOL_MANAGER"],
          memberships: [membership(1, 10, "ثانوية الأندلس", ["SCHOOL_MANAGER"])],
        }),
      },
      "/school/sms/absences/preview/": { body: messagePreview },
    });

    const user = userEvent.setup();
    renderApp("/attendance/absence-messages");

    const editor = await screen.findByLabelText("نص رسالة الغياب الموحد");
    expect(editor).toHaveValue(template);
    expect(screen.getByText("أكمل رمزي الاسم والتاريخ مرة واحدة لعرض المعاينة.")).toBeInTheDocument();

    await user.click(editor);
    await user.keyboard("{End}");
    await user.click(screen.getByRole("button", { name: /«اسم الطالب».*إضافة/ }));
    await user.click(screen.getByRole("button", { name: /«التاريخ».*إضافة/ }));

    expect(editor).toHaveValue(`${template}«اسم الطالب»«التاريخ»`);
    expect(screen.getByText(new RegExp(`${template}أحمد\\d{4}-\\d{2}-\\d{2}`))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "حفظ القالب لجميع الطلاب" })).toBeEnabled();
  });

  it.each(["UNKNOWN", "ACCEPTED"] as const)("shows %s delivery without offering a resend", async (status) => {
    mockApi({
      "/auth/me/": {
        body: buildMe({
          active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
          roles: ["SCHOOL_MANAGER"],
          memberships: [membership(1, 10, "ثانوية الأندلس", ["SCHOOL_MANAGER"])],
        }),
      },
      "/school/sms/absences/preview/": {
        body: {
          ...messagePreview,
          total: 1,
          candidate_student_ids: [1],
          students: [{
            student_id: 1,
            full_name: "طالب تجريبي",
            grade_name: "الثاني الثانوي",
            section_name: "أ",
            absence_status: "FULL",
            submitted_periods: 1,
            expected_periods: 1,
            recipient_masked: "***1234",
            eligibility_reason: null,
            send_status: status,
            send_error: status === "UNKNOWN" ? "DREAMS_RESPONSE_UNKNOWN" : "",
          }],
        },
      },
    });

    renderApp("/attendance/absence-messages");

    if (status === "UNKNOWN") {
      expect(await screen.findByText(/لم نتأكد من إرسال الرسالة/)).toHaveTextContent(
        "تحقق من «الرسائل المرسلة» في حساب دريمز قبل إعادة إرسالها",
      );
    } else {
      expect(await screen.findByText("قبله المزود")).toBeInTheDocument();
      expect(screen.queryByText(/لم نتأكد من إرسال الرسالة/)).not.toBeInTheDocument();
    }
    expect(screen.queryByText(/DREAMS_RESPONSE_UNKNOWN/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /مراجعة إرسال 0 من 0 محدد/ })).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: "اختيار طالب تجريبي" }));
    expect(screen.getByRole("button", { name: /مراجعة إرسال 0 من 1 محدد/ })).toBeDisabled();
  });
});

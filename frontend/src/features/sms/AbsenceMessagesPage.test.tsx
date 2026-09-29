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
});
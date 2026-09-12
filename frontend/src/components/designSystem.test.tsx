import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { Button } from "@/components/Button";
import { Modal } from "@/components/Modal";
import { PageSkeleton } from "@/components/Skeleton";
import { TextField } from "@/components/TextField";

function ModalHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>فتح الحوار</button>
      {open && (
        <Modal title="تأكيد الإجراء" description="راجع البيانات قبل الحفظ." onClose={() => setOpen(false)}>
          <TextField label="ملاحظة" data-dialog-initial-focus />
          <Button>حفظ</Button>
        </Modal>
      )}
    </>
  );
}

describe("Design system primitives", () => {
  it("exposes a clear loading state without changing the action contract", () => {
    render(<Button loading loadingLabel="جارٍ الحفظ...">حفظ</Button>);
    const button = screen.getByRole("button", { name: "جارٍ الحفظ..." });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("connects labels, help text, required state, and validation errors", () => {
    const { rerender } = render(<TextField label="اسم المدرسة" required description="الاسم الرسمي المعتمد." />);
    const input = screen.getByRole("textbox", { name: /اسم المدرسة/ });
    expect(input).toBeRequired();
    expect(input).toHaveAccessibleDescription("الاسم الرسمي المعتمد.");

    rerender(<TextField label="اسم المدرسة" required error="هذا الحقل مطلوب." />);
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("هذا الحقل مطلوب.");
  });

  it("moves focus into dialogs, closes with Escape, and restores focus", async () => {
    const user = userEvent.setup();
    render(<ModalHarness />);
    const opener = screen.getByRole("button", { name: "فتح الحوار" });
    await user.click(opener);

    const dialog = screen.getByRole("dialog", { name: "تأكيد الإجراء" });
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
    expect(screen.getByRole("textbox", { name: "ملاحظة" })).toHaveFocus();
    expect(document.body.style.overflow).toBe("hidden");

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
    expect(document.body.style.overflow).toBe("");
  });

  it("announces skeleton loading without exposing decorative blocks", () => {
    render(<PageSkeleton label="جارٍ تحميل الاختبار" />);
    expect(screen.getByRole("status")).toHaveTextContent("جارٍ تحميل الاختبار");
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
  });
});

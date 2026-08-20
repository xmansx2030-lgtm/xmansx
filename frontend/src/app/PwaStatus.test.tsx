import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PwaStatus } from "@/app/PwaStatus";

const pwa = vi.hoisted(() => ({
  needRefresh: true,
  offlineReady: false,
  setNeedRefresh: vi.fn(),
  setOfflineReady: vi.fn(),
  updateServiceWorker: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("virtual:pwa-register/react", () => ({
  useRegisterSW: () => ({
    needRefresh: [pwa.needRefresh, pwa.setNeedRefresh],
    offlineReady: [pwa.offlineReady, pwa.setOfflineReady],
    updateServiceWorker: pwa.updateServiceWorker,
  }),
}));

describe("PWA status UX", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
  });

  it("lets the user choose when to apply an available update", async () => {
    const user = userEvent.setup();
    render(<PwaStatus />);

    expect(screen.getByText("يتوفر تحديث جديد للمنصة.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "تحديث الآن" }));
    expect(pwa.updateServiceWorker).toHaveBeenCalledWith(true);

    await user.click(screen.getByRole("button", { name: "تأجيل التحديث" }));
    expect(pwa.setNeedRefresh).toHaveBeenCalledWith(false);
  });

  it("shows a clear no-fake-success warning when connectivity is lost", async () => {
    render(<PwaStatus />);
    await act(() => window.dispatchEvent(new Event("offline")));

    expect(
      await screen.findByText("تعذر الاتصال. لن تُعتمد أي عملية حتى يعود الاتصال."),
    ).toBeInTheDocument();
  });
});

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PwaInstallPrompt } from "@/app/PwaInstallPrompt";

function mockDisplayMode(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockReturnValue({
      matches,
      media: "(display-mode: standalone)",
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

describe("PWA install prompt", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    const values = new Map<string, string>();
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: {
        clear: () => values.clear(),
        getItem: (key: string) => values.get(key) ?? null,
        removeItem: (key: string) => values.delete(key),
        setItem: (key: string, value: string) => values.set(key, value),
      },
    });
    mockDisplayMode(false);
    vi.spyOn(window.navigator, "userAgent", "get").mockReturnValue("Mozilla/5.0 Android Chrome");
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("shows the premium prompt and invokes the native browser installer", async () => {
    const prompt = vi.fn().mockResolvedValue(undefined);
    const event = new Event("beforeinstallprompt", { cancelable: true }) as Event & {
      prompt: () => Promise<void>;
      userChoice: Promise<{ outcome: "accepted"; platform: string }>;
    };
    event.prompt = prompt;
    event.userChoice = Promise.resolve({ outcome: "accepted", platform: "web" });

    render(<PwaInstallPrompt />);
    act(() => {
      window.dispatchEvent(event);
      vi.advanceTimersByTime(1_200);
    });

    expect(screen.getByRole("dialog", { name: "ثبّت منصة المواظبة" })).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("install-pwa"));
    await act(async () => undefined);
    expect(prompt).toHaveBeenCalledOnce();
  });

  it("shows Safari instructions on iPhone and remembers Later", () => {
    vi.spyOn(window.navigator, "userAgent", "get").mockReturnValue("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) AppleWebKit Safari");
    render(<PwaInstallPrompt />);
    act(() => vi.advanceTimersByTime(1_200));

    expect(screen.getByTestId("ios-install-steps")).toHaveTextContent("إضافة إلى الشاشة الرئيسية");
    fireEvent.click(screen.getByRole("button", { name: "لاحقًا" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(Number(localStorage.getItem("pwa-install-dismissed-until"))).toBeGreaterThan(Date.now());
  });

  it("does not interrupt users who already opened the installed app", () => {
    mockDisplayMode(true);
    render(<PwaInstallPrompt />);
    act(() => vi.advanceTimersByTime(2_000));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

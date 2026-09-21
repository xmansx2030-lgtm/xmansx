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
    Object.defineProperty(window.navigator, "maxTouchPoints", { configurable: true, value: 0 });
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
    expect(screen.getByTestId("ios-install-steps")).toHaveTextContent("إذا لم يظهر الخيار، افتح الصفحة في Safari");
    expect(screen.getByTestId("pwa-offline-note")).toHaveTextContent("حفظ أي عملية يتطلب اتصالًا بالإنترنت");
    fireEvent.click(screen.getByRole("button", { name: "لاحقًا" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(Number(localStorage.getItem("pwa-install-dismissed-until"))).toBeGreaterThan(Date.now());
  });

  it("keeps iOS manual instructions even if a wrapper dispatches beforeinstallprompt", () => {
    vi.spyOn(window.navigator, "userAgent", "get").mockReturnValue("Mozilla/5.0 (iPad; CPU OS 18_0) AppleWebKit Safari");
    render(<PwaInstallPrompt />);
    act(() => {
      window.dispatchEvent(new Event("beforeinstallprompt", { cancelable: true }));
      vi.advanceTimersByTime(1_200);
    });

    expect(screen.getByTestId("ios-install-steps")).toBeInTheDocument();
    expect(screen.queryByTestId("install-pwa")).toBeNull();
  });

  it("recognizes modern iPadOS devices that identify as Macintosh", () => {
    vi.spyOn(window.navigator, "userAgent", "get").mockReturnValue(
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit Safari",
    );
    Object.defineProperty(window.navigator, "maxTouchPoints", { configurable: true, value: 5 });
    render(<PwaInstallPrompt />);
    act(() => vi.advanceTimersByTime(1_200));

    expect(screen.getByTestId("ios-install-steps")).toBeInTheDocument();
  });

  it("shows manual Android steps when the browser has no native install event", () => {
    vi.spyOn(window.navigator, "userAgent", "get").mockReturnValue("Mozilla/5.0 (Android 15; Mobile; rv:142.0) Gecko/142.0 Firefox/142.0");
    render(<PwaInstallPrompt />);

    act(() => vi.advanceTimersByTime(3_999));
    expect(screen.queryByRole("dialog")).toBeNull();
    act(() => vi.advanceTimersByTime(1));

    expect(screen.getByTestId("android-install-steps")).toHaveTextContent("تثبيت التطبيق");
    expect(screen.getByTestId("android-install-steps")).toHaveTextContent("إضافة إلى الشاشة الرئيسية");
  });

  it("redirects embedded mobile browsers to Safari or Chrome", () => {
    vi.spyOn(window.navigator, "userAgent", "get").mockReturnValue("Mozilla/5.0 (Linux; Android 15; wv) WhatsApp");
    render(<PwaInstallPrompt />);
    act(() => vi.advanceTimersByTime(1_200));

    expect(screen.getByTestId("embedded-browser-steps")).toHaveTextContent("فتح في Safari");
    expect(screen.getByTestId("embedded-browser-steps")).toHaveTextContent("فتح في Chrome");
    expect(screen.queryByTestId("install-pwa")).toBeNull();
  });

  it("does not interrupt users who already opened the installed app", () => {
    mockDisplayMode(true);
    render(<PwaInstallPrompt />);
    act(() => vi.advanceTimersByTime(2_000));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

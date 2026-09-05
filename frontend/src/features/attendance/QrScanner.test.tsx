import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { extractQrToken, QrScanner } from "@/features/attendance/QrScanner";

const scanner = vi.hoisted(() => ({
  callback: null as null | ((result: { getText: () => string } | undefined, error: unknown, controls: { stop: () => void }) => void),
  controls: { stop: vi.fn(), switchTorch: vi.fn().mockResolvedValue(undefined) },
  decodeFromConstraints: vi.fn(),
  decodeFromImageUrl: vi.fn(),
}));

vi.mock("@zxing/browser", () => ({
  BrowserQRCodeReader: class {
    decodeFromConstraints(constraints: MediaStreamConstraints, video: HTMLVideoElement, callback: typeof scanner.callback) {
      scanner.callback = callback;
      Object.defineProperty(video, "readyState", { configurable: true, value: 3 });
      Object.defineProperty(video, "videoWidth", { configurable: true, value: 1280 });
      return scanner.decodeFromConstraints(constraints);
    }

    decodeFromImageUrl(url: string) {
      return scanner.decodeFromImageUrl(url);
    }
  },
}));

describe("QR mobile scanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    scanner.callback = null;
    scanner.decodeFromConstraints.mockResolvedValue(scanner.controls);
    scanner.decodeFromImageUrl.mockResolvedValue({ getText: () => "https://school.test/qr/photo-token-123" });
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn() },
    });
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn().mockReturnValue("blob:qr") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  });

  it("extracts tokens only from platform QR values", () => {
    expect(extractQrToken("https://school.test/qr/valid-token_123")).toBe("valid-token_123");
    expect(extractQrToken("raw-token-123")).toBe("raw-token-123");
    expect(extractQrToken("https://example.test/not-a-qr")).toBeNull();
  });

  it("requests the rear camera and opens the scanned section token", async () => {
    const onToken = vi.fn();
    render(<QrScanner onToken={onToken} onClose={vi.fn()} />);

    await waitFor(() => expect(scanner.decodeFromConstraints).toHaveBeenCalledOnce());
    const constraints = scanner.decodeFromConstraints.mock.calls[0]?.[0] as MediaStreamConstraints;
    expect(constraints.audio).toBe(false);
    expect(constraints.video).toMatchObject({ facingMode: { ideal: "environment" } });

    act(() => scanner.callback?.({ getText: () => "https://school.test/qr/live-token-456" }, null, scanner.controls));
    expect(onToken).toHaveBeenCalledWith("live-token-456");
    expect(scanner.controls.stop).toHaveBeenCalled();
  });

  it("centers the scan frame independently from the RTL page direction", async () => {
    render(<QrScanner onToken={vi.fn()} onClose={vi.fn()} />);
    await waitFor(() => expect(scanner.decodeFromConstraints).toHaveBeenCalledOnce());

    const frame = screen.getByTestId("qr-scan-frame");
    expect(frame).toHaveClass("left-1/2", "top-1/2", "-translate-x-1/2", "-translate-y-1/2");
    expect(frame).not.toHaveClass("inset-1/2");
  });

  it("explains denied camera permission and keeps the image capture fallback", async () => {
    scanner.decodeFromConstraints.mockRejectedValue(new DOMException("Denied", "NotAllowedError"));
    render(<QrScanner onToken={vi.fn()} onClose={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("إذن الكاميرا مرفوض");
    const capture = screen.getByLabelText("التقاط صورة لرمز QR");
    expect(capture).toHaveAttribute("capture", "environment");
  });

  it("decodes a captured mobile photo when live video is unavailable", async () => {
    scanner.decodeFromConstraints.mockRejectedValue(new DOMException("Denied", "NotAllowedError"));
    const onToken = vi.fn();
    render(<QrScanner onToken={onToken} onClose={vi.fn()} />);
    await screen.findByRole("alert");

    const image = new File(["qr"], "qr.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("التقاط صورة لرمز QR"), { target: { files: [image] } });
    await waitFor(() => expect(onToken).toHaveBeenCalledWith("photo-token-123"));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:qr");
  });
});

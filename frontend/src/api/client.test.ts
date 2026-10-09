import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiRequest } from "@/api/client";

describe("apiRequest", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("parses unified error bodies into ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ code: "NOT_FOUND", message: "المورد المطلوب غير موجود.", details: {} }),
          { status: 404, headers: { "X-Request-ID": "req-1234-abcd" } },
        ),
      ),
    );

    const error = await apiRequest("/missing/").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.code).toBe("NOT_FOUND");
    expect(apiError.status).toBe(404);
    expect(apiError.message).toBe("المورد المطلوب غير موجود.");
    expect(apiError.requestId).toBe("req-1234-abcd");
  });

  it("returns parsed JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "ok" }), { status: 200 })),
    );
    await expect(apiRequest<{ status: string }>("/health/")).resolves.toEqual({ status: "ok" });
  });

  it("passes Retry-After to the polling and retry policies", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ code: "RATE_LIMITED", message: "حاول لاحقاً", details: {} }),
      { status: 429, headers: { "Retry-After": "30" } },
    )));
    const error = await apiRequest("/reports/absence/").catch((value: unknown) => value);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).retryAfterMs).toBe(30_000);
  });

  it("maps network failures to a NETWORK_ERROR ApiError with Arabic message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await apiRequest("/health/").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("NETWORK_ERROR");
  });

  it("sends X-CSRFToken header on mutating requests", async () => {
    document.cookie = "csrftoken=csrf-test-value";
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await apiRequest("/auth/logout/", { method: "POST" });
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Record<string, string>)["X-CSRFToken"]).toBe("csrf-test-value");
  });

  it("sends credentials for session cookies", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await apiRequest("/health/");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/health/",
      expect.objectContaining({ credentials: "include" }),
    );
  });
  it("uploads multipart files with session credentials and CSRF without forcing JSON headers", async () => {
    document.cookie = "csrftoken=upload-token";
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 7 })));
    vi.stubGlobal("fetch", fetchMock);
    const body = new FormData(); body.append("file", new File(["report"], "report.pdf", { type: "application/pdf" }));
    await apiRequest("/parent/children/11/excuses/1/attachments/", { method: "POST", body });
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.body).toBe(body);
    expect(init.credentials).toBe("include");
    expect(init.headers).toEqual({ "X-CSRFToken": "upload-token" });
  });
});

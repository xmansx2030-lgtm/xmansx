import { purgeSensitiveBrowserCaches } from "@/app/cacheSafety";
import { mockBrowserStorage } from "@/test/browserStorage";

describe("PWA private cache safety", () => {
  beforeEach(() => mockBrowserStorage());
  afterEach(() => vi.unstubAllGlobals());

  it("removes API and private file responses while preserving static assets", async () => {
    window.localStorage.setItem("attendance-draft:v1:1:10:5", "private draft");
    window.localStorage.setItem("unrelated-preference", "keep");
    const apiRequest = new Request("https://app.example.test/api/v1/students/1/");
    const mediaRequest = new Request("https://app.example.test/media/excuses/private.pdf");
    const assetRequest = new Request("https://app.example.test/assets/index-fingerprint.js");
    const requests = [apiRequest, mediaRequest, assetRequest];
    const deletedUrls: string[] = [];
    const deleteRequest = vi.fn(async (request: Request) => {
      deletedUrls.push(request.url);
      return true;
    });
    const cache = { keys: vi.fn().mockResolvedValue(requests), delete: deleteRequest };
    const cacheStorage = {
      keys: vi.fn().mockResolvedValue(["legacy-runtime-cache"]),
      open: vi.fn().mockResolvedValue(cache),
    };
    vi.stubGlobal("caches", cacheStorage);

    await purgeSensitiveBrowserCaches();

    expect(deleteRequest).toHaveBeenCalledTimes(2);
    expect(deletedUrls).toEqual([apiRequest.url, mediaRequest.url]);
    expect(deletedUrls).not.toContain(assetRequest.url);
    expect(window.localStorage.getItem("attendance-draft:v1:1:10:5")).toBeNull();
    expect(window.localStorage.getItem("unrelated-preference")).toBe("keep");
  });

  it("can purge private responses while preserving same-account teacher drafts for email verification", async () => {
    const draftKey = "attendance-draft:v1:1:10:5";
    window.localStorage.setItem(draftKey, "teacher draft");
    const privateRequest = new Request("https://app.example.test/api/v1/parent/children/1/");
    const deleteRequest = vi.fn().mockResolvedValue(true);
    vi.stubGlobal("caches", {
      keys: vi.fn().mockResolvedValue(["legacy-runtime-cache"]),
      open: vi.fn().mockResolvedValue({ keys: vi.fn().mockResolvedValue([privateRequest]), delete: deleteRequest }),
    });
    await purgeSensitiveBrowserCaches({ preserveAttendanceDrafts: true });
    expect(deleteRequest).toHaveBeenCalledExactlyOnceWith(privateRequest);
    expect(window.localStorage.getItem(draftKey)).toBe("teacher draft");
  });
});

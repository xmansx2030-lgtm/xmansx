import { purgeSensitiveBrowserCaches } from "@/app/cacheSafety";

describe("PWA private cache safety", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("removes API and private file responses while preserving static assets", async () => {
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
  });
});

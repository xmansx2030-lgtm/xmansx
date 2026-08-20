const PRIVATE_PATH_PREFIXES = ["/api/", "/media/", "/private/"];

function isPrivateRequest(request: Request): boolean {
  const url = new URL(request.url);
  return PRIVATE_PATH_PREFIXES.some((prefix) => url.pathname.startsWith(prefix));
}

/** Remove sensitive responses left by any older or misconfigured service worker version. */
export async function purgeSensitiveBrowserCaches(): Promise<void> {
  if (!("caches" in globalThis)) return;

  const cacheNames = await globalThis.caches.keys();
  await Promise.all(
    cacheNames.map(async (cacheName) => {
      const cache = await globalThis.caches.open(cacheName);
      const requests = await cache.keys();
      await Promise.all(
        requests.filter(isPrivateRequest).map((request) => cache.delete(request)),
      );
    }),
  );
}

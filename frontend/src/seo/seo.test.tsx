import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queryClient } from "@/app/queryClient";
import { renderApp } from "@/test/renderApp";
import { buildMe, mockApi, UNAUTHENTICATED } from "@/test/mockApi";
import { PUBLIC_FEATURES } from "./content";
import { updatePageSeo } from "./SeoLayout";
import { getPublicPage, getStructuredData, normalizeSiteUrl, PRIVATE_ROBOTS, serializeJsonLd, SITE_URL } from "./site";

describe("Public discovery and private route metadata", () => {
  beforeEach(() => { queryClient.clear(); });
  afterEach(() => { updatePageSeo("/login"); });

  it.each(["http://example.com", "https://example.com/path", "https://example.com/?token=secret", "https://example.com/#fragment", "https://user:password@example.com"])("rejects unsafe canonical origin %s", (origin) => {
    expect(() => normalizeSiteUrl(origin)).toThrow();
  });

  it("normalizes HTTPS origins without inventing localized URLs", () => {
    expect(normalizeSiteUrl("https://mowadhabah.com/")).toBe("https://mowadhabah.com");
    expect(new Set(PUBLIC_FEATURES.map((feature) => feature.path)).size).toBe(PUBLIC_FEATURES.length);
    for (const feature of PUBLIC_FEATURES) {
      expect(getPublicPage(feature.path)?.title).toBe(feature.title);
      expect(getStructuredData(feature.path)?.["@graph"].at(-1)?.["@type"]).toBe("BreadcrumbList");
    }
  });

  it.each(["/students/42/attendance", "/parent/activate", "/parent/invitation", "/qr/secret-token", "/login", "/features/unknown", "/features/reports/nested"])("does not publish canonical or structured data for %s", (path) => {
    updatePageSeo("/features/reports");
    expect(document.querySelector('link[rel="canonical"]')).not.toBeNull();
    updatePageSeo(path);
    expect(getPublicPage(path)).toBeUndefined();
    expect(getStructuredData(path)).toBeNull();
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute("content", PRIVATE_ROBOTS);
    expect(document.querySelector('link[rel="canonical"]')).toBeNull();
    expect(document.querySelector('meta[property="og:url"]')).toBeNull();
    expect(document.querySelector('script[type="application/ld+json"]')).toBeNull();
  });

  it("escapes script delimiters and keeps real structured data free of invented ratings or offers", () => {
    expect(serializeJsonLd({ value: "</script><script>alert(1)</script>&" })).not.toContain("<");
    const schema = JSON.stringify(getStructuredData("/"));
    expect(schema).not.toMatch(/aggregateRating|offers|SearchAction/);
    expect(schema).toContain(`${SITE_URL}/#organization`);
  });

  it("lets visitors read the homepage even while the session API is pending", () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => String(input).includes("/auth/me/")
      ? new Promise<Response>(() => {})
      : Promise.resolve(new Response("[]", { headers: { "Content-Type": "application/json" } }))));
    renderApp("/");
    expect(screen.getByRole("heading", { name: /كل تفاصيل المواظبة/ })).toBeInTheDocument();
  });

  it("keeps the signed-in account destination", async () => {
    mockApi({ "/auth/me/": { body: buildMe({ is_platform_admin: true }) }, "/auth/registration/plans/": { body: [] } });
    renderApp("/");
    await waitFor(() => expect(document.querySelector('link[rel="canonical"]')).toBeNull());
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute("content", PRIVATE_ROBOTS);
  });

  it("renders readable feature content and removes public metadata on login navigation", async () => {
    mockApi({ "/auth/me/": UNAUTHENTICATED });
    const feature = PUBLIC_FEATURES[0]!;
    renderApp(feature.path);
    expect(await screen.findByRole("heading", { level: 1, name: feature.label })).toBeInTheDocument();
    expect(document.querySelector('link[rel="canonical"]')).toHaveAttribute("href", `${SITE_URL}${feature.path}`);
    await userEvent.setup().click(screen.getByRole("link", { name: "تسجيل الدخول" }));
    await waitFor(() => expect(document.querySelector('link[rel="canonical"]')).toBeNull());
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute("content", PRIVATE_ROBOTS);
  });

  it("preserves viewport and PWA metadata when SEO changes", () => {
    const viewport = document.createElement("meta");
    viewport.name = "viewport";
    viewport.content = "width=device-width, initial-scale=1.0";
    document.head.append(viewport);
    updatePageSeo("/");
    expect(viewport.isConnected).toBe(true);
    viewport.remove();
  });

  it("uses the private shell for PWA navigation and leaves discovery files to the network", () => {
    const config = readFileSync(resolve(process.cwd(), "vite.config.ts"), "utf8");
    expect(config).toContain('navigateFallback: "app.html"');
    expect(config).toContain("robots\\.txt");
    expect(config).toContain("sitemap\\.xml");
  });
});

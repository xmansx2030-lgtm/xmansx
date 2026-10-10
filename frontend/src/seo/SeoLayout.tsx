import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { getPublicPage, getStructuredData, PRIVATE_ROBOTS, PUBLIC_ROBOTS, SEARCH_INDEXING, serializeJsonLd, SHARE_IMAGE, SITE_NAME, SITE_URL } from "./site";

export function updatePageSeo(pathname: string) {
  const page = getPublicPage(pathname);
  // Own only SEO tags; PWA, viewport and security metadata stay untouched.
  document.head.querySelectorAll('[data-seo], meta[name="description"], meta[name="robots"], link[rel="canonical"]').forEach((tag) => tag.remove());
  document.title = page?.title ?? SITE_NAME;
  const meta = (attribute: "name" | "property", name: string, content: string) => {
    const element = document.createElement("meta");
    element.setAttribute(attribute, name);
    element.content = content;
    element.dataset.seo = "";
    document.head.append(element);
  };
  meta("name", "robots", page && SEARCH_INDEXING ? PUBLIC_ROBOTS : PRIVATE_ROBOTS);
  if (!page) return;
  meta("name", "description", page.description);
  const canonical = document.createElement("link");
  canonical.rel = "canonical";
  canonical.href = `${SITE_URL}${page.path}`;
  canonical.dataset.seo = "";
  document.head.append(canonical);
  for (const [name, content] of Object.entries({
    "og:type": "website", "og:locale": "ar_SA", "og:site_name": SITE_NAME,
    "og:title": page.title, "og:description": page.description, "og:url": canonical.href,
    "og:image": SHARE_IMAGE, "og:image:alt": SITE_NAME, "og:image:width": "512", "og:image:height": "512",
  })) meta("property", name, content);
  for (const [name, content] of Object.entries({ "twitter:card": "summary", "twitter:title": page.title, "twitter:description": page.description, "twitter:image": SHARE_IMAGE, "twitter:image:alt": SITE_NAME })) meta("name", name, content);
  const schema = document.createElement("script");
  schema.type = "application/ld+json";
  schema.dataset.seo = "";
  schema.textContent = serializeJsonLd(getStructuredData(pathname));
  document.head.append(schema);
}

export function SeoLayout() {
  const { pathname } = useLocation();
  useEffect(() => { updatePageSeo(pathname); }, [pathname]);
  return <Outlet />;
}

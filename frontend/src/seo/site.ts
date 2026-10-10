import { PUBLIC_FEATURES } from "./content";

export const SITE_NAME = "منصة المواظبة";
export const PRIVATE_ROBOTS = "noindex, nofollow, nosnippet";
export const PUBLIC_ROBOTS = "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1";

export function normalizeSiteUrl(value: string): string {
  const url = new URL(value);
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error("VITE_SITE_URL must be an HTTPS origin without credentials, a path, query or fragment.");
  }
  return url.origin;
}

export const SITE_URL = normalizeSiteUrl(import.meta.env.VITE_SITE_URL || "https://mowadhabah.com");
export const SEARCH_INDEXING = import.meta.env.PROD && import.meta.env.VITE_SEARCH_INDEXING !== "false";
export const SHARE_IMAGE = `${SITE_URL}/icons/pwa-512.png`;

export const PUBLIC_PAGES = [
  {
    path: "/",
    label: SITE_NAME,
    title: "منصة المواظبة | إدارة الحضور والغياب والمتابعة الطلابية",
    description: "منصة المواظبة لإدارة الحضور والغياب والتأخر الصباحي والمتابعة الطلابية والتقارير المدرسية، مع بوابة ولي الأمر وصلاحيات لفريق المدرسة وواجهة عربية للجوال والحاسوب.",
  },
  ...PUBLIC_FEATURES,
];

export function getPublicPage(pathname: string) {
  // Only exact public paths can acquire indexing metadata. Tokens and unknown paths cannot.
  return PUBLIC_PAGES.find((page) => page.path === pathname);
}

export function getStructuredData(pathname: string) {
  const page = getPublicPage(pathname);
  if (!page) return null;
  const url = `${SITE_URL}${page.path}`;
  const organization = { "@type": "Organization", "@id": `${SITE_URL}/#organization`, name: SITE_NAME, url: `${SITE_URL}/`, logo: SHARE_IMAGE };
  const website = { "@type": "WebSite", "@id": `${SITE_URL}/#website`, name: SITE_NAME, url: `${SITE_URL}/`, inLanguage: "ar-SA", publisher: { "@id": organization["@id"] } };
  const webPage = { "@type": "WebPage", "@id": `${url}#webpage`, url, name: page.title, description: page.description, inLanguage: "ar-SA", isPartOf: { "@id": website["@id"] }, about: { "@id": organization["@id"] } };
  const breadcrumbs = {
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: SITE_NAME, item: `${SITE_URL}/` },
      { "@type": "ListItem", position: 2, name: page.label, item: url },
    ],
  };
  return { "@context": "https://schema.org", "@graph": pathname === "/" ? [organization, website, webPage] : [organization, website, webPage, breadcrumbs] };
}

export function serializeJsonLd(value: unknown): string {
  return JSON.stringify(value).replace(/</g, "\\u003c").replace(/>/g, "\\u003e").replace(/&/g, "\\u0026");
}

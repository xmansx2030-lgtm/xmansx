import { createHash } from "node:crypto";
import { readFile, rm } from "node:fs/promises";
import { resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import react from "@vitejs/plugin-react";
import { build, loadEnv } from "vite";

// Render the actual React public pages before the client/PWA build. No browser,
// production API, credentials or extra runtime service is required to build.
const root = process.cwd();
const modeIndex = process.argv.indexOf("--mode");
const mode = modeIndex >= 0 ? process.argv[modeIndex + 1] : "production";
if (!mode) throw new Error("Missing build mode");
const env = { ...loadEnv(mode, root, "VITE_"), ...Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("VITE_"))) };
const temporaryDirectory = resolve(root, "tmp/seo-render");
if (!temporaryDirectory.startsWith(`${root}${sep}`)) throw new Error("SEO temporary directory is outside the frontend workspace");
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));

try {
  await build({
    configFile: false, root, mode, logLevel: "warn", plugins: [react()],
    resolve: { alias: { "@": resolve(root, "src") } },
    define: { "import.meta.env": JSON.stringify({ ...env, PROD: true, DEV: false, MODE: mode, BASE_URL: "/" }) },
    build: { ssr: "src/seo/entry-server.tsx", outDir: temporaryDirectory, emptyOutDir: true, rollupOptions: { output: { entryFileNames: "render.mjs" } } },
  });
  const seo = await import(pathToFileURL(resolve(temporaryDirectory, "render.mjs")).href);
  const { PUBLIC_PAGES, SITE_URL, SITE_NAME, SHARE_IMAGE, SEARCH_INDEXING, PRIVATE_ROBOTS, PUBLIC_ROBOTS } = seo;
  const meta = (name, content, attribute = "name") => `<meta data-seo ${attribute}="${escapeHtml(name)}" content="${escapeHtml(content)}" />`;
  const schemaHashes = [];
  function publicHead(page) {
    const canonical = `${SITE_URL}${page.path}`;
    const jsonLd = seo.serializeJsonLd(seo.getStructuredData(page.path));
    schemaHashes.push(`'sha256-${createHash("sha256").update(jsonLd).digest("base64")}'`);
    return [
      `<title>${escapeHtml(page.title)}</title>`,
      meta("description", page.description), meta("robots", SEARCH_INDEXING ? PUBLIC_ROBOTS : PRIVATE_ROBOTS),
      `<link data-seo rel="canonical" href="${escapeHtml(canonical)}" />`,
      ...Object.entries({ "og:type": "website", "og:locale": "ar_SA", "og:site_name": SITE_NAME, "og:title": page.title, "og:description": page.description, "og:url": canonical, "og:image": SHARE_IMAGE, "og:image:alt": SITE_NAME, "og:image:width": "512", "og:image:height": "512" }).map(([name, value]) => meta(name, value, "property")),
      ...Object.entries({ "twitter:card": "summary", "twitter:title": page.title, "twitter:description": page.description, "twitter:image": SHARE_IMAGE, "twitter:image:alt": SITE_NAME }).map(([name, value]) => meta(name, value)),
      ...(env.VITE_GOOGLE_SITE_VERIFICATION ? [`<meta name="google-site-verification" content="${escapeHtml(env.VITE_GOOGLE_SITE_VERIFICATION)}" />`] : []),
      ...(env.VITE_BING_SITE_VERIFICATION ? [`<meta name="msvalidate.01" content="${escapeHtml(env.VITE_BING_SITE_VERIFICATION)}" />`] : []),
      `<script data-seo type="application/ld+json">${jsonLd}</script>`,
    ].join("\n    ");
  }
  const securityHeaders = await readFile(resolve(root, "infra-security-headers.conf"), "utf8");
  const routesSource = await readFile(resolve(root, "src/routes/index.tsx"), "utf8");
  // Derive protected route prefixes from the application's route inventory so new
  // school/parent routes retain direct navigation without becoming indexable.
  const privatePrefixes = [...new Set([...routesSource.matchAll(/path:\s*"\/?([^"/*:]+)/g)].map((match) => match[1]))].sort();
  if (!privatePrefixes.includes("login") || !privatePrefixes.includes("parent")) throw new Error("Could not read private route inventory");
  const headers = `include /etc/nginx/snippets/xmansx-security-headers.conf;\n    include /etc/nginx/snippets/xmansx-indexing.conf;\n    add_header Cache-Control "no-cache" always;`;
  const publicLocations = PUBLIC_PAGES.map((page) => {
    const file = page.path === "/" ? "/index.html" : `${page.path}.html`;
    return `location = ${page.path} {\n    default_type text/html;\n    ${headers}\n    try_files ${file} =404;\n}\n${page.path === "/" ? "" : `location = ${page.path}/ { return 301 ${page.path}$is_args$args; }\n`}`;
  }).join("\n");
  const nginxLocations = `${publicLocations}\nlocation ~ ^/(?:${privatePrefixes.join("|")})(?:/|$) {\n    default_type text/html;\n    ${headers}\n    add_header X-Robots-Tag "${PRIVATE_ROBOTS}" always;\n    try_files /app.html =404;\n}\n`;

  await build({
    root, mode,
    plugins: [{
      name: "prerender-public-seo",
      enforce: "post",
      generateBundle(_options, bundle) {
        const index = bundle["index.html"];
        if (!index || index.type !== "asset") throw new Error("Missing built index.html");
        const template = String(index.source);
        if (!template.includes("<!--seo-head:start-->") || !template.includes('<div id="root"></div>')) throw new Error("SEO template markers missing");
        const fontPreloads = Object.keys(bundle).filter((file) => /ibm-plex-sans-arabic-arabic-(400|700)-normal-[^/]+\.woff2$/.test(file)).map((file) => `<link rel="preload" href="/${file}" as="font" type="font/woff2" crossorigin />`).join("\n");
        const render = (head, body) => template.replace(/<!--seo-head:start-->[\s\S]*?<!--seo-head:end-->/, () => `${head}\n${fontPreloads}`).replace('<div id="root"></div>', () => `<div id="root">${body}</div>`);
        this.emitFile({ type: "asset", fileName: "app.html", source: template });
        for (const page of PUBLIC_PAGES) {
          const source = render(publicHead(page), seo.renderPublicPage(page.path));
          if (page.path === "/") index.source = source;
          else this.emitFile({ type: "asset", fileName: `${page.path.slice(1)}.html`, source });
        }
        this.emitFile({ type: "asset", fileName: "404.html", source: render(`<title>الصفحة غير موجودة | ${SITE_NAME}</title>\n${meta("robots", PRIVATE_ROBOTS)}`, seo.renderPublicPage("/not-found")) });
        // Auth pages are crawlable so crawlers can read noindex. robots.txt is not
        // access control; APIs/media are authenticated independently by Django.
        const robots = SEARCH_INDEXING
          ? `User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /media/\n\nSitemap: ${SITE_URL}/sitemap.xml\n`
          : "User-agent: *\nDisallow: /\n";
        const sitemap = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${(SEARCH_INDEXING ? PUBLIC_PAGES : []).map((page) => `  <url><loc>${escapeHtml(`${SITE_URL}${page.path}`)}</loc></url>`).join("\n")}\n</urlset>\n`;
        this.emitFile({ type: "asset", fileName: "robots.txt", source: robots });
        this.emitFile({ type: "asset", fileName: "sitemap.xml", source: sitemap });
        this.emitFile({ type: "asset", fileName: ".nginx/seo-locations.conf", source: nginxLocations });
        this.emitFile({ type: "asset", fileName: ".nginx/security-headers.conf", source: securityHeaders.replace("script-src 'self'", `script-src 'self' ${[...new Set(schemaHashes)].join(" ")}`) });
        this.emitFile({ type: "asset", fileName: ".nginx/indexing.conf", source: SEARCH_INDEXING ? "# Production public indexing is enabled.\n" : `add_header X-Robots-Tag "${PRIVATE_ROBOTS}" always;\n` });
      },
    }],
  });
  process.stdout.write(`SEO: ${PUBLIC_PAGES.length} public HTML pages, robots.txt and sitemap.xml; indexing ${SEARCH_INDEXING ? "enabled" : "disabled"}.\n`);
} finally {
  await rm(temporaryDirectory, { recursive: true, force: true });
}

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";

const root = resolve(process.cwd(), "dist");
const read = (file) => readFile(resolve(root, file), "utf8");
const robots = await read("robots.txt");
const indexing = !robots.includes("Disallow: /\n");
const sitemap = new JSDOM(await read("sitemap.xml"), { contentType: "application/xml" }).window.document;
const locations = [...sitemap.querySelectorAll("loc")].map((node) => node.textContent);
assert.equal(locations.length, indexing ? 6 : 0);
assert.equal(new Set(locations).size, locations.length);
assert(locations.every((url) => !/parent\/activate|students|login|token|register/.test(url)));
const security = await read(".nginx/security-headers.conf");
assert(!security.includes("unsafe-inline"));
const files = ["index.html", ...(await readdir(resolve(root, "features"))).map((name) => `features/${name}`)];
const canonicals = new Set();
const titles = new Set();
for (const file of files) {
  const document = new JSDOM(await read(file)).window.document;
  assert.equal(document.querySelectorAll("h1").length, 1, file);
  assert.equal(document.documentElement.lang, "ar");
  assert.equal(document.documentElement.dir, "rtl");
  assert(document.querySelector("#root").textContent.length > 500, `${file}: readable content without JS`);
  assert.equal(document.querySelectorAll('link[rel="canonical"]').length, 1);
  const canonical = document.querySelector('link[rel="canonical"]').href;
  assert.equal(new URL(canonical).protocol, "https:");
  assert(!new URL(canonical).search);
  canonicals.add(canonical);
  titles.add(document.title);
  assert(document.querySelector('meta[name="description"]').content.length > 50);
  assert.equal(document.querySelector('meta[property="og:url"]').content, canonical);
  assert.equal(document.querySelector('meta[name="robots"]').content.startsWith("index,"), indexing);
  const script = document.querySelector('script[type="application/ld+json"]');
  assert(JSON.parse(script.textContent)["@graph"].some((item) => item["@type"] === "WebPage"));
  const hash = createHash("sha256").update(script.textContent).digest("base64");
  assert(security.includes(`'sha256-${hash}'`), `${file}: CSP authorizes only the generated JSON-LD`);
  if (indexing) assert(locations.includes(canonical), file);
  for (const featureLink of document.querySelectorAll('a[href^="/features/"]')) {
    assert(files.includes(`${featureLink.getAttribute("href").slice(1)}.html`), "Every public link has real HTML");
  }
}
assert.equal(canonicals.size, files.length);
assert.equal(titles.size, files.length);
for (const file of ["app.html", "404.html"]) {
  const document = new JSDOM(await read(file)).window.document;
  assert(document.querySelector('meta[name="robots"]').content.includes("noindex"));
  assert.equal(document.querySelector('link[rel="canonical"]'), null);
  assert.equal(document.querySelector('script[type="application/ld+json"]'), null);
}
const serviceWorker = await read("sw.js");
assert(serviceWorker.includes("app.html"));
assert(!serviceWorker.includes('url:"index.html"'), "The redirected HTML alias must not prevent SW installation");
assert(!serviceWorker.includes('url:"404.html"'));
assert(!/url:"features\//.test(serviceWorker));
process.stdout.write(`SEO artifact verification passed: ${files.length} readable public pages; ${indexing ? "production" : "noindex"} build; private shell, sitemap, canonical URLs and CSP.\n`);

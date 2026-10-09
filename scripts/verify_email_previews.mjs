// Local Chromium checks. All message links are synthetic and are never clicked.
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve, join } from 'node:path';
import { parseArgs } from 'node:util';

const { values } = parseArgs({ options: {
  frontend: { type: 'string' }, previews: { type: 'string' },
} });
const require = createRequire(join(resolve(values.frontend), 'package.json'));
const { chromium } = require('playwright');
const previews = resolve(values.previews);
const entries = JSON.parse(await readFile(join(previews, 'manifest.json'), 'utf8'));
const shots = join(previews, 'screenshots');
await mkdir(shots, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];
try {
  for (const mode of ['normal', 'inline-only', 'long-values']) {
    for (const width of [1366, 768, 390]) {
      for (const entry of entries) {
        const page = await browser.newPage({ viewport: { width, height: 900 }, locale: 'ar-SA' });
        const errors = [], network = [];
        page.on('pageerror', e => errors.push(e.message));
        await page.route('**/*', route => {
          network.push(route.request().url());
          return route.abort();
        });
        let content = await readFile(join(previews, entry.file), 'utf8');
        if (mode === 'inline-only') content = content.replace(/<style>[\s\S]*?<\/style>/g, '');
        if (mode === 'long-values') {
          content = content.replaceAll('مدرسة الأفق النموذجية', 'مدرسة ' + 'م'.repeat(255))
            .replaceAll('الباقة السنوية', 'ب'.repeat(255));
        }
        await page.setContent(content);
        await page.evaluate(() => document.fonts.ready);
        const metrics = await page.evaluate(() => {
          const button = document.querySelector('a');
          const rect = button?.getBoundingClientRect();
          return {
            pageWidth: document.documentElement.clientWidth,
            scrollWidth: Math.max(document.body.scrollWidth, document.documentElement.scrollWidth),
            headings: document.querySelectorAll('h1').length,
            direction: getComputedStyle(document.body).direction,
            buttonHeight: rect?.height, buttonWidth: rect?.width,
            buttonRight: rect?.right, buttonLeft: rect?.left,
          };
        });
        assert.equal(errors.length, 0, `${entry.kind}: page errors`);
        assert.equal(network.length, 0, `${entry.kind}: external resources`);
        assert.equal(metrics.headings, 1);
        assert.equal(metrics.direction, 'rtl');
        assert.ok(metrics.scrollWidth <= metrics.pageWidth + 1,
          `${entry.kind}/${width}/${mode}: horizontal overflow ${JSON.stringify(metrics)}`);
        assert.ok(metrics.buttonHeight >= 44, `${entry.kind}: small button`);
        assert.ok(metrics.buttonLeft >= 0 && metrics.buttonRight <= width,
          `${entry.kind}: clipped action`);
        if (mode === 'normal') {
          await page.screenshot({ path: join(shots, `${entry.kind.toLowerCase()}-${width}.png`),
            fullPage: true, timeout: 60000 });
        }
        results.push({ kind: entry.kind, width, mode, ...metrics, errors, externalRequests: network });
        await page.close();
      }
    }
  }
} finally {
  await browser.close();
}
await writeFile(join(previews, 'browser-verification.json'), JSON.stringify(results, null, 2));
console.log(`${results.length} browser cases passed; 30 screenshots; no outbound requests.`);

import { execFileSync, execSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** قبل كل تشغيل E2E: fixtures بهويات فريدة + إعادة البذر (حتمية النتائج).
 *  إعادة seed_dev تعيد إسناد «جدول التطوير (24 حصة)» لكل أيام الأسبوع — فتصحح
 *  ما غيّره settings.spec في تشغيل سابق (وإلا فلا حصة حالية بعد ظهر اليوم). */
export default function globalSetup() {
  const here = dirname(fileURLToPath(import.meta.url));
  const repoRoot = resolve(here, "..", "..");
  const script = resolve(repoRoot, "scripts", "generate_e2e_fixtures.py");
  const venvPython = resolve(repoRoot, "backend", ".venv", "Scripts", "python.exe");
  // ‏E2E_PYTHON: worktree موازٍ بلا venv خاص به يستعير مفسر الشجرة الرئيسية
  const python =
    process.env.E2E_PYTHON ?? (existsSync(venvPython) ? venvPython : "python");
  execFileSync(python, [script], { stdio: "inherit" });

  const password = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";
  // ‏E2E_COMPOSE_PROJECT: يوجه البذر إلى حزمة Docker الخاصة بهذه الشجرة حتى لا
  // تلمس حزمة شجرة أخرى تعمل بالتوازي (تطوير مراحل متزامن)
  const project = process.env.E2E_COMPOSE_PROJECT;
  const compose = project ? `docker compose -p ${project}` : "docker compose";
  execSync(
    `${compose} exec -T backend python manage.py seed_dev --password "${password}"`,
    { cwd: repoRoot, stdio: "inherit" },
  );

  return warmFrontend();
}

/** تسخين خادم التطوير قبل أول اختبار.
 *
 * ‏Vite يعيد تجميع الاعتماديات عند أول طلب بعد تغيّر شجرة المصادر، وطلبات الوحدات
 * أثناء ذلك قد ترجع 504 فتظهر صفحة فارغة للمتصفح. جلب الصفحة والوحدة الجذرية مرة
 * قبل التشغيل يجعل ذلك يحدث خارج أي اختبار.
 */
async function warmFrontend() {
  const base = process.env.E2E_BASE_URL ?? "http://localhost:5173";
  for (const path of ["/", "/src/main.tsx"]) {
    for (let attempt = 0; attempt < 30; attempt += 1) {
      try {
        const response = await fetch(`${base}${path}`);
        await response.text();
        if (response.ok) break;
      } catch {
        // الخادم لم يجهز بعد
      }
      await new Promise((done) => setTimeout(done, 1000));
    }
  }
}

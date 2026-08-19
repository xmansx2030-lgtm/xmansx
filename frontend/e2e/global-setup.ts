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
  const python = existsSync(venvPython) ? venvPython : "python";
  execFileSync(python, [script], { stdio: "inherit" });

  const password = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";
  execSync(
    `docker compose exec -T backend python manage.py seed_dev --password "${password}"`,
    { cwd: repoRoot, stdio: "inherit" },
  );
}

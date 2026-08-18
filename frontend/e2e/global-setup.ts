import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** يولد fixtures نور بهويات فريدة قبل كل تشغيل E2E (حتمية النتائج). */
export default function globalSetup() {
  const here = dirname(fileURLToPath(import.meta.url));
  const repoRoot = resolve(here, "..", "..");
  const script = resolve(repoRoot, "scripts", "generate_e2e_fixtures.py");
  const venvPython = resolve(repoRoot, "backend", ".venv", "Scripts", "python.exe");
  const python = existsSync(venvPython) ? venvPython : "python";
  execFileSync(python, [script], { stdio: "inherit" });
}

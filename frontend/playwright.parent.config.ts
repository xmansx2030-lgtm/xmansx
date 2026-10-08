import { defineConfig, devices } from "@playwright/test";
import { createHash, X509Certificate } from "node:crypto";
import { readFileSync, realpathSync } from "node:fs";
import { resolve } from "node:path";
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:5173";
const serverAddress = new URL(baseURL);
if (!["localhost", "127.0.0.1", "[::1]"].includes(serverAddress.hostname)) {
  throw new Error("Parent E2E requires an isolated localhost origin.");
}
const preview = process.env.PARENT_E2E_PREVIEW === "1";
const externalPreview = process.env.PARENT_E2E_EXTERNAL_PREVIEW === "1";
if (externalPreview && (baseURL !== "https://localhost:8445" || process.env.PARENT_E2E_SYNTHETIC_STAGING !== "1")) {
  throw new Error("External parent preview is restricted to the synthetic localhost TLS stack.");
}
const localCertificatePath = resolve("..", "artifacts", "parent-staging", "localhost.crt");
if (externalPreview && (!process.env.NODE_EXTRA_CA_CERTS || realpathSync(process.env.NODE_EXTRA_CA_CERTS) !== realpathSync(localCertificatePath))) {
  throw new Error("Synthetic TLS API requests require only the generated localhost certificate in NODE_EXTRA_CA_CERTS.");
}
const localCertificate = externalPreview
  ? new X509Certificate(readFileSync(localCertificatePath))
  : undefined;
if (localCertificate && localCertificate.checkHost("localhost") !== "localhost") {
  throw new Error("Synthetic TLS certificate must match localhost.");
}
// Chromium's service-worker installer needs certificate trust beyond context
// ignoreHTTPSErrors. Trust only this generated local certificate's SPKI.
const localSPKI = localCertificate
  ? createHash("sha256").update(localCertificate.publicKey.export({ type: "spki", format: "der" })).digest("base64")
  : undefined;
export default defineConfig({
  testDir: "./e2e",
  testMatch: "parent-portal.spec.ts",
  workers: 1,
  timeout: 90_000,
  reporter: [["list"]],
  use: {
    baseURL, trace: "retain-on-failure", timezoneId: "Asia/Riyadh", ignoreHTTPSErrors: false,
    launchOptions: { args: localSPKI ? [`--ignore-certificate-errors-spki-list=${localSPKI}`] : [] },
  },
  webServer: externalPreview ? undefined : {
    command: `npm run ${preview ? "preview" : "dev"} -- --host ${serverAddress.hostname} --port ${serverAddress.port || "5173"} --strictPort`,
    url: baseURL,
    reuseExistingServer: true,
    timeout: 60_000,
  },
  projects: [
    { name: "chromium-parent", use: { ...devices["Desktop Chrome"] } },
  ],
});

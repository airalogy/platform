import { spawnSync } from "node:child_process"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"

export const aiIndependentSpecs = [
  "first-record",
  "analysis-protocol-drafts",
  "analysis-publication",
  "project-analysis",
  "record-analysis-selection",
  "workflow-assets",
  "workflow-canvas",
  "workflow-project-analysis",
].map(name => `tests/e2e/specs/${name}.spec.ts`)

export function runBrowserMatrix(run = spawnSync, environment = process.env) {
  for (const [mode, files] of [["enabled", []], ["disabled", aiIndependentSpecs]]) {
    const result = run("corepack", ["pnpm", "e2e", ...files], {
      cwd: fileURLToPath(new URL("../", import.meta.url)),
      stdio: "inherit",
      env: {
        ...environment,
        AI_ENABLED: mode === "enabled" ? "true" : "false",
        // Each real API instance must start from an independent disposable DB.
        E2E_KEEP_INFRA: "0",
        E2E_OUTPUT_DIR: `test-results/ai-${mode}`,
        E2E_HTML_REPORT_DIR: `playwright-report/ai-${mode}`,
      },
    })
    if (result.error)
      throw result.error
    if (result.status !== 0)
      return result.status ?? 1
  }
  return 0
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv.length !== 2)
    throw new Error("The full browser matrix does not accept filters; use pnpm e2e for a focused run")
  process.exitCode = runBrowserMatrix()
}

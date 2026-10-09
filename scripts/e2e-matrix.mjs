import { spawnSync } from "node:child_process"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { parseArgs } from "node:util"

export const aiIndependentSpecs = [
  "first-record",
  "record-import",
  "client-assigner-export",
  "analysis-protocol-drafts",
  "analysis-publication",
  "project-analysis",
  "record-analysis-selection",
  "workflow-assets",
  "workflow-canvas",
  "workflow-project-analysis",
].map(name => `tests/e2e/specs/${name}.spec.ts`)

export function browserModes({ mode, shard } = {}) {
  if (mode !== undefined && !["enabled", "disabled"].includes(mode))
    throw new Error("Browser mode must be enabled or disabled")
  if (shard !== undefined) {
    if (!mode || !/^[1-9]\d*\/[1-9]\d*$/.test(shard))
      throw new Error("A shard requires an explicit mode and index/total")
    const [index, total] = shard.split("/").map(Number)
    if (index > total || total > 16)
      throw new Error("Invalid browser shard range")
  }
  return ["enabled", "disabled"].filter(value => !mode || mode === value)
}

export function runBrowserMatrix(run = spawnSync, environment = process.env, options = {}) {
  for (const mode of browserModes(options)) {
    const files = mode === "enabled" ? [] : aiIndependentSpecs
    const suffix = options.shard ? `-${options.shard.replace("/", "-of-")}` : ""
    const result = run("corepack", ["pnpm", "e2e", ...files, ...(options.shard ? [`--shard=${options.shard}`] : [])], {
      cwd: fileURLToPath(new URL("../", import.meta.url)),
      stdio: "inherit",
      env: {
        ...environment,
        AI_ENABLED: mode === "enabled" ? "true" : "false",
        // Each real API instance must start from an independent disposable DB.
        E2E_KEEP_INFRA: "0",
        E2E_OUTPUT_DIR: `test-results/ai-${mode}${suffix}`,
        E2E_HTML_REPORT_DIR: `playwright-report/ai-${mode}${suffix}`,
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
  const { values } = parseArgs({ options: { mode: { type: "string" }, shard: { type: "string" } }, allowPositionals: false })
  process.exitCode = runBrowserMatrix(spawnSync, process.env, values)
}

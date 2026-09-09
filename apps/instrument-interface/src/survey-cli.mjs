#!/usr/bin/env node
import { parseArgs } from "node:util"
import { bytesDigest, canonical } from "./contract.mjs"
import { readPrivateSelection } from "./evidence.mjs"
import { assemblePreparedSurvey, prepareSurvey, runPreparedSurvey } from "./survey-workspace.mjs"

async function main() {
  const strings = ["selection", "file", "url", "application", "version", "title", "locale", "scope-role", "scope-name", "scope-test-id", "network", "redact", "workspace", "confirm", "analysis"]
  const { values, positionals } = parseArgs({ allowPositionals: true, options: { ...Object.fromEntries(strings.map(key => [key, { type: "string" }])), "capture-values": { type: "boolean", default: false }, "screenshot": { type: "boolean", default: false } } })
  let result
  if (positionals[0] === "prepare" && positionals.length === 1) {
    let selected
    if (values.selection) {
      if (Object.keys(values).some(key => !["selection", "workspace", "capture-values", "screenshot"].includes(key)) || values["capture-values"] || values.screenshot)
        throw new Error("Use the selected JSON's exact capture policy without overrides")
      selected = JSON.parse(await readPrivateSelection(values.selection))
    }
    else {
      if (values.confirm || values.analysis)
        throw new Error("Prepare does not accept analysis or launch confirmation")
      if (Boolean(values.file) === Boolean(values.url) || (values["scope-test-id"] && (values["scope-role"] || values["scope-name"])))
        throw new Error("Select exactly one source and one scope")
      const source = values.file ? { kind: "file", path: values.file, sha256: bytesDigest(await readPrivateSelection(values.file, 1048576)) } : { kind: "url", url: values.url }
      selected = {
        schema: "airalogy.interface-survey-selection.v1",
        id: "selected.application",
        target: { application: values.application, version: values.version, title: values.title, locale: values.locale || "en-US", source, scope: values["scope-test-id"] ? { kind: "test_id", name: values["scope-test-id"] } : { kind: "role", role: values["scope-role"] || "main", name: values["scope-name"] || "" } },
        network: values.network ? JSON.parse(await readPrivateSelection(values.network)) : source.kind === "url" ? [{ url: source.url, method: "GET", max_requests: 1 }] : [],
        blocked: [],
        privacy: { screenshot: values.screenshot, redact: values.redact ? JSON.parse(await readPrivateSelection(values.redact)) : [] },
        capture_values: values["capture-values"],
        limits: { duration_seconds: 60, max_steps: 1, step_timeout_ms: 5000, viewport: { width: 1280, height: 900 } },
      }
    }
    result = await prepareSurvey(selected, values.workspace)
  }
  else if (positionals[0] === "run" && positionals.length === 2) {
    if (Object.keys(values).some(key => !["confirm", "capture-values", "screenshot"].includes(key)) || values["capture-values"] || values.screenshot)
      throw new Error("Run only the saved selection without overrides")
    result = await runPreparedSurvey(positionals[1], values.confirm)
  }
  else if (positionals[0] === "assemble" && positionals.length === 2) {
    if (Object.keys(values).some(key => !["analysis", "workspace", "capture-values", "screenshot"].includes(key)) || values["capture-values"] || values.screenshot)
      throw new Error("Assembly does not accept execution or capture options")
    result = await assemblePreparedSurvey(positionals[1], values.analysis, values.workspace)
  }
  else {
    throw new Error("Use prepare with an explicit source, application/version/title, scope and private workspace; run REQUEST --confirm DIGEST; assemble REQUEST --analysis FILE --workspace PATH")
  }
  process.stdout.write(`${canonical(result)}\n`)
}
main().catch(() => {
  process.stderr.write("Survey stopped. Check the exact selection, capture policy and private evidence. Retain run.started; never retry an uncertain launch. No hardware safety is established.\n")
  process.exitCode = 1
})

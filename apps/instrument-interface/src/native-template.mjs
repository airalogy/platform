import { Buffer } from "node:buffer"
import { join } from "node:path"
import { canonical } from "./contract.mjs"
import { Evidence } from "./evidence.mjs"
import { previewNativeInterface, validateNativeInterface } from "./native-session.mjs"
import { selectNative } from "./native-survey.mjs"
import { validateNativeBuild } from "./native-transport.mjs"

// A reviewable fixture contract, not a vendor adapter generated from a survey.
export function nativeSimulationTemplate(selection) {
  const locator = (role, name) => ({ kind: "ax_identifier", role, name })
  const definition = validateNativeInterface({
    schema: "airalogy.native-interface.v1",
    id: "owned.native.reader",
    selection,
    target: { application: selection.target.application, version: selection.target.version, title: selection.target.title, locale: selection.target.locale, source: { kind: "native_macos_simulation" }, identity: { locator: locator("AXStaticText", "app.identity"), text: "Airalogy Native Reader 1.0 — simulation only" } },
    controls: [
      { id: "sample_count", locator: locator("AXTextField", "sample.count"), read: "value", operations: ["read", "fill"] },
      { id: "run", locator: locator("AXButton", "run.simulation"), read: "text", operations: ["click"] },
      { id: "status", locator: locator("AXStaticText", "reader.status"), read: "text", operations: ["read"] },
      { id: "result", locator: locator("AXStaticText", "reader.result"), read: "text", operations: ["read"] },
    ],
    states: [{ id: "ready", checks: [{ control_id: "status", equals: "Ready" }] }, { id: "complete", checks: [{ control_id: "status", equals: "Complete" }] }],
    limits: { duration_seconds: 120, max_steps: 5, step_timeout_ms: 10000 },
  })
  const actions = [{ operation: "fill", control_id: "sample_count", value: "2", before: "ready", after: "ready" }, { operation: "click", control_id: "run", before: "ready", after: "complete" }]
  // The result is independently specified, not copied from the observed output.
  const success = [{ control_id: "status", equals: "Complete" }, { control_id: "sample_count", equals: "2" }, { control_id: "result", equals: "0.84" }]
  definition.states[1].checks.push(...success.slice(1))
  return { definition, plan: { schema: "airalogy.interface-plan.v1", steps: actions }, policy: { goal: "Set two synthetic samples, run the owned simulation, and verify the independently expected result 0.84. No hardware is connected.", actions, success } }
}

export async function prepareNativeSimulation({ buildFile, pid, workspace }) {
  const { directory } = await validateNativeBuild(buildFile)
  const selection = await selectNative({ buildFile, bundlePath: join(directory, "AiralogyNativeReader.app"), pid, title: "Airalogy Native Reader — Simulation", captureValues: true, redactIdentifiers: ["private.note"] })
  const template = nativeSimulationTemplate(selection)
  const preview = await previewNativeInterface(template.definition, template.plan)
  const evidence = await Evidence.create(workspace, preview)
  for (const name of ["definition", "plan", "policy"])
    await evidence.write(`${name}.json`, Buffer.from(canonical(template[name])))
  return { definition_file: join(evidence.directory, "definition.json"), plan_file: join(evidence.directory, "plan.json"), policy_file: join(evidence.directory, "policy.json"), preview_digest: preview.sha256, actions_executed: 0, hardware_qualified: false }
}

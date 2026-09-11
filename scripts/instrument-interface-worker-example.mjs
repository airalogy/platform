// Owned, network-disabled HTML only. No model or foreground desktop access.
import { Buffer } from "node:buffer"
import { mkdtemp } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { fileURLToPath } from "node:url"
import { BrowserInterfaceSession, previewInterface } from "../apps/instrument-interface/src/browser-session.mjs"
import { canonical, digest } from "../apps/instrument-interface/src/contract.mjs"
import { BrowserDemonstrationSession, previewDemonstration } from "../apps/instrument-interface/src/demonstration.mjs"
import { Evidence } from "../apps/instrument-interface/src/evidence.mjs"
import { prepareWorkerRuntime, previewWorkerRuntime } from "../apps/instrument-interface/src/worker-runtime.mjs"
import { workflowFromEvidence } from "../apps/instrument-interface/src/workflow.mjs"
import { createExample } from "./instrument-interface-example.mjs"

export async function createWorkerExample(root, { demonstration = false } = {}) {
  const { definition, plan } = await createExample()
  definition.privacy.screenshot = false
  const policy = { goal: "Read two owned synthetic samples", actions: plan.steps, success: [{ control_id: "result.value", equals: "0.84" }] }
  const empty = { schema: "airalogy.interface-plan.v1", steps: [] }
  const preview = demonstration ? await previewDemonstration(definition, policy, { visible: false }) : await previewInterface(definition, empty, policy)
  const session = demonstration
    ? await BrowserDemonstrationSession.open({ definition, policy, confirmation: preview.sha256, evidenceRoot: root, visible: false, acknowledgeOwnedSimulation: true })
    : await BrowserInterfaceSession.open({ definition, plan: empty, policy, confirmation: preview.sha256, evidenceRoot: root })
  try {
    if (demonstration) {
      // Test-generated browser events exercise the recorder path, not evidence
      // of an actual human's identity or a physical instrument demonstration.
      const field = session.page.getByRole("spinbutton", { name: "Synthetic sample count" })
      await field.click()
      await field.press("ControlOrMeta+A")
      await field.pressSequentially("2")
      await field.press("Tab")
      await session.page.waitForFunction(key => !window[key].busy && !window[key].pending, session.statusKey)
      if (session.cursor !== 1)
        throw new Error("Synthetic fill was not recorded")
      await session.page.getByRole("button", { name: "Run simulation" }).click()
      await session.page.waitForFunction(key => !window[key].busy, session.statusKey)
      if (session.cursor !== 2)
        throw new Error("Synthetic click was not recorded")
    }
    else {
      await session.step(digest(session.lastObservation), 0)
      await session.step(digest(session.lastObservation), 1)
    }
    if (session.lastObservation.values["result.value"] !== "0.84")
      throw new Error("Independent owned-fixture result failed")
    if (demonstration)
      await session.finish()
    else
      await session.evidence.append("exploration_result", { result: "client_reported_success", proposal: { kind: "finish", action_index: null, summary: "Owned deterministic fixture, not a model call", missing_information: [] }, hardware_qualified: false })
  }
  finally { await session.close() }
  const workflow = await workflowFromEvidence(session.evidence.directory)
  const evidence = await Evidence.create(root, { owned_fixture_only: true })
  await evidence.write("workflow.json", Buffer.from(canonical(workflow)))
  const file = join(evidence.directory, "workflow.json")
  const runtime = await previewWorkerRuntime(file, root)
  // Automatic confirmation is confined to this source-owned fixture command.
  return prepareWorkerRuntime(file, { evidenceRoot: root, workspace: root, confirmation: runtime.sha256 })
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  if (process.argv.length !== 2 && (process.argv.length !== 3 || process.argv[2] !== "--demonstration"))
    throw new Error("The owned example accepts no target or executable overrides")
  const root = await mkdtemp(join(tmpdir(), "airalogy-interface-worker-"))
  process.stdout.write(`${canonical(await createWorkerExample(root, { demonstration: process.argv[2] === "--demonstration" }))}\n`)
}

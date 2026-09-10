// Owned, network-disabled HTML only. No model or foreground desktop access.
import { Buffer } from "node:buffer"
import { mkdtemp } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { fileURLToPath } from "node:url"
import { BrowserInterfaceSession, previewInterface } from "../apps/instrument-interface/src/browser-session.mjs"
import { canonical, digest } from "../apps/instrument-interface/src/contract.mjs"
import { Evidence } from "../apps/instrument-interface/src/evidence.mjs"
import { prepareWorkerRuntime, previewWorkerRuntime } from "../apps/instrument-interface/src/worker-runtime.mjs"
import { workflowFromEvidence } from "../apps/instrument-interface/src/workflow.mjs"
import { createExample } from "./instrument-interface-example.mjs"

export async function createWorkerExample(root) {
  const { definition, plan } = await createExample()
  definition.privacy.screenshot = false
  const policy = { goal: "Read two owned synthetic samples", actions: plan.steps, success: [{ control_id: "result.value", equals: "0.84" }] }
  const empty = { schema: "airalogy.interface-plan.v1", steps: [] }
  const preview = await previewInterface(definition, empty, policy)
  const session = await BrowserInterfaceSession.open({ definition, plan: empty, policy, confirmation: preview.sha256, evidenceRoot: root })
  try {
    await session.step(digest(session.lastObservation), 0)
    await session.step(digest(session.lastObservation), 1)
    if (session.lastObservation.values["result.value"] !== "0.84")
      throw new Error("Independent owned-fixture result failed")
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
  if (process.argv.length !== 2)
    throw new Error("The owned example accepts no target or executable overrides")
  const root = await mkdtemp(join(tmpdir(), "airalogy-interface-worker-"))
  process.stdout.write(`${canonical(await createWorkerExample(root))}\n`)
}

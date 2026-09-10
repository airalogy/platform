#!/usr/bin/env node
// Trusted one-shot local worker. The installed Python client validates all
// runtime bytes/resolution links before starting Node with a clean environment.
import { Buffer } from "node:buffer"
import { release } from "node:os"
import { BrowserInterfaceSession, previewInterface } from "./browser-session.mjs"
import { bytesDigest, canonical, checkObject } from "./contract.mjs"
import { Evidence, readPrivateSelection } from "./evidence.mjs"
import { previewWorkflow, runWorkflow, validateWorkflow } from "./workflow.mjs"

async function main() {
  if (process.argv.length !== 2)
    throw new Error("Worker accepts one bounded request on stdin only")
  const chunks = []
  let size = 0
  for await (const part of process.stdin) {
    size += part.length
    if (size > 8192)
      throw new Error("Worker request exceeded its bound")
    chunks.push(part)
  }
  const request = JSON.parse(Buffer.concat(chunks))
  checkObject(request, ["schema", "operation", "job_id", "runtime_file", "runtime_sha256", "workflow_digest"])
  if (request.schema !== "airalogy.interface-worker-request.v1" || !["probe", "execute"].includes(request.operation) || (request.operation === "probe" ? request.job_id !== null : typeof request.job_id !== "string" || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(request.job_id)))
    throw new Error("Unsupported worker operation")
  const raw = await readPrivateSelection(request.runtime_file, 2097152)
  if (bytesDigest(raw) !== request.runtime_sha256)
    throw new Error("Worker runtime descriptor changed")
  const runtime = JSON.parse(raw)
  const workflowBytes = await readPrivateSelection(runtime.workflow.path, 524288)
  if (bytesDigest(workflowBytes) !== runtime.workflow.sha256)
    throw new Error("Workflow bytes changed")
  const workflow = validateWorkflow(JSON.parse(workflowBytes))
  if (workflow.sha256 !== request.workflow_digest || workflow.sha256 !== runtime.workflow.workflow_digest || workflow.definition.schema !== "airalogy.browser-interface.v1")
    throw new Error("Worker selection differs from the installed configuration")
  const evidence = await Evidence.create(runtime.evidence_root, { schema: request.schema, operation: request.operation, job_id: request.job_id, runtime_sha256: request.runtime_sha256, workflow_digest: workflow.sha256 })
  await evidence.append("worker_intent", { operation: request.operation, job_id: request.job_id, workflow_digest: workflow.sha256, hardware_qualified: false })
  let data
  if (request.operation === "probe") {
    const plan = { schema: "airalogy.interface-plan.v1", steps: [] }
    const preview = await previewInterface(workflow.definition, plan)
    const session = await BrowserInterfaceSession.open({ definition: workflow.definition, plan, confirmation: preview.sha256, evidenceRoot: evidence.directory, browserExecutable: runtime.browser })
    try {
      const { target, state, values, enabled } = session.lastObservation
      data = { target: { identity_reference: `interface:${workflow.definition.target.source.kind === "file" ? workflow.definition.target.source.sha256 : workflow.sha256}`, firmware: "not_applicable", application: target.application, application_version: target.version, driver_version: `interface-worker-v1:${request.runtime_sha256.slice(0, 16)}`, os_version: `${process.platform}:${process.arch}:${release()}` }, initial_matches: canonical({ state, values, enabled }) === canonical(workflow.initial), source_kind: workflow.definition.target.source.kind }
    }
    finally { await session.close() }
  }
  else {
    const preview = await previewWorkflow(workflow)
    const result = await runWorkflow(workflow, { confirmation: preview.sha256, evidenceRoot: evidence.directory, acknowledgeNewRun: true, browserExecutable: runtime.browser })
    data = { values: result.values, session_id: result.session_id, source_kind: workflow.definition.target.source.kind }
  }
  const response = { schema: "airalogy.interface-worker-response.v1", operation: request.operation, job_id: request.job_id, runtime_sha256: request.runtime_sha256, workflow_digest: workflow.sha256, data, hardware_qualified: false }
  await evidence.append("worker_result", response)
  process.stdout.write(`${canonical(response)}\n`)
}
main().catch(() => {
  // Do not emit selected UI text, paths, raw browser failures or credentials.
  process.stderr.write("Selected interface worker failed; reconcile private evidence without replay.\n")
  process.exitCode = 1
})

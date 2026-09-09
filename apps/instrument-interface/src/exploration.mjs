import { Buffer } from "node:buffer"
import { randomBytes, randomUUID } from "node:crypto"
import { lstat, open, readdir } from "node:fs/promises"
import { dirname, join } from "node:path"
import { BrowserInterfaceSession, previewInterface } from "./browser-session.mjs"
import { bytesDigest, canonical, digest, exactUrl } from "./contract.mjs"
import { Evidence, readPrivateSelection, syncDirectory } from "./evidence.mjs"
import { fingerprint, shape, validateObservation, validateProposal, validateRequest } from "./exploration-contract.mjs"

const emptyPlan = { schema: "airalogy.interface-plan.v1", steps: [] }
function platformBase(value) {
  const url = new URL(exactUrl(value))
  if (url.search)
    throw new Error("Platform API base must not contain a query")
  return value
}
export async function prepareExploration({ definition, policy, workspace, platformUrl, gatewayId, resourceId, maxIterations = 5, durationSeconds = 600 }) {
  platformBase(platformUrl)
  const preview = await previewInterface(definition, emptyPlan, policy)
  const request = {
    schema: "airalogy.interface-exploration.v1",
    id: randomUUID(),
    gateway_id: gatewayId,
    resource_id: resourceId,
    credential_digest: "0".repeat(64),
    fingerprint: "0".repeat(64),
    max_iterations: maxIterations,
    duration_seconds: durationSeconds,
    spec: {
      goal: policy.goal,
      local_preview_digest: preview.sha256,
      target: { application: definition.target.application, version: definition.target.version, kind: definition.target.source.kind },
      controls: definition.controls.map(control => ({ id: control.id, label: control.locator.name || control.id, read: control.read })),
      states: definition.states,
      actions: policy.actions,
      success: policy.success,
    },
  }
  const token = `aiinterface_${randomBytes(32).toString("base64url")}`
  request.credential_digest = bytesDigest(token)
  request.fingerprint = fingerprint(request)
  validateRequest(request)
  const evidence = await Evidence.create(workspace, preview)
  await evidence.write("authorization.json", Buffer.from(canonical(request)))
  await evidence.write("request.json", Buffer.from(canonical({ request, token, platform_url: platformUrl, definition: preview.definition, policy: preview.policy })))
  return { request_file: join(evidence.directory, "request.json"), authorization_file: join(evidence.directory, "authorization.json"), fingerprint: request.fingerprint, local_preview_digest: preview.sha256 }
}

async function readRequest(path) {
  const info = await lstat(path)
  const parent = await lstat(dirname(path))
  if (process.platform === "win32" || !info.isFile() || info.isSymbolicLink() || info.nlink !== 1 || (info.mode & 0o077) || info.uid !== process.getuid() || !parent.isDirectory() || parent.isSymbolicLink() || parent.uid !== process.getuid() || (parent.mode & 0o077))
    throw new Error("Exploration credentials require owner-only POSIX files and directory")
  const content = JSON.parse(await readPrivateSelection(path, 524288))
  if (!content || Object.keys(content).sort().join(",") !== "definition,platform_url,policy,request,token" || !/^aiinterface_[\w-]{43}$/.test(content.token))
    throw new Error("Invalid private exploration request")
  validateRequest(content.request)
  if (content.request.credential_digest !== bytesDigest(content.token))
    throw new Error("Exploration credential changed")
  platformBase(content.platform_url)
  return content
}

export class InterfaceClient {
  constructor(content) {
    this.content = content
  }

  async call(operation, payload = {}, turnId = null) {
    if (!["status", "turns", "report", "end"].includes(operation) || (operation === "report" && !/^[0-9a-f-]{36}$/.test(turnId)))
      throw new Error("Unsupported interface-development API operation")
    const suffix = operation === "report" ? `turns/${turnId}/report` : operation
    const response = await fetch(`${this.content.platform_url.replace(/\/$/, "")}/instrument-exploration/${this.content.request.id}/${suffix}`, {
      method: "POST",
      redirect: "error",
      signal: AbortSignal.timeout(70000),
      headers: { "Content-Type": "application/json", "X-Airalogy-Interface-Token": this.content.token },
      body: canonical(payload),
    })
    const chunks = []
    let size = 0
    for await (const part of response.body) {
      size += part.length
      if (size > 2097152)
        throw new Error("Interface API response exceeded its limit")
      chunks.push(part)
    }
    if (!response.ok)
      throw new Error(`Interface API rejected the request (HTTP ${response.status}); retain local evidence`)
    return JSON.parse(Buffer.concat(chunks).toString("utf8"))
  }
}

function observed(session, request) {
  const current = session.lastObservation
  return validateObservation({ session_id: current.session_id, sequence: session.cursor, local_preview_digest: request.spec.local_preview_digest, state: current.state, values: current.values, enabled: current.enabled }, request.spec)
}

async function authorized(client, request) {
  const status = await client.call("status")
  if (status.can_proceed !== true || status.effective_state !== "open" || canonical(status.request) !== canonical(request) || !Number.isFinite(Date.parse(status.expires_at)) || Date.parse(status.expires_at) <= Date.now())
    throw new Error("Interface authorization changed, expired or was cancelled")
  return status
}

export async function runExploration(path, { confirmation, client = null } = {}) {
  const content = await readRequest(path)
  const { request } = content
  const preview = await previewInterface(content.definition, emptyPlan, content.policy)
  if (confirmation !== preview.sha256 || preview.sha256 !== request.spec.local_preview_digest)
    throw new Error("Review and confirm the exact local application/action policy before launch")
  const controls = content.definition.controls.map(control => ({ id: control.id, label: control.locator.name || control.id, read: control.read }))
  const target = { application: content.definition.target.application, version: content.definition.target.version, kind: content.definition.target.source.kind }
  if (content.policy.goal !== request.spec.goal || canonical(target) !== canonical(request.spec.target) || canonical(controls) !== canonical(request.spec.controls) || canonical(content.definition.states) !== canonical(request.spec.states) || canonical(content.policy.actions) !== canonical(request.spec.actions) || canonical(content.policy.success) !== canonical(request.spec.success))
    throw new Error("Local selection no longer matches the remote grant")
  client ??= new InterfaceClient(content)
  const initial = await authorized(client, request)
  if (!Array.isArray(initial.turns) || initial.turns.length)
    throw new Error("This grant already has saved turns; sync reports without relaunching")
  const root = dirname(path)
  // Never relaunch/replay an uncertain session after restart. This exclusive marker remains.
  const lock = await open(join(root, "run.started"), "wx", 0o600)
  try {
    await lock.writeFile(request.fingerprint)
    await lock.sync()
  }
  finally {
    await lock.close()
  }
  await syncDirectory(root)
  let session = null
  let lastTurnId = null
  let result = "stopped"
  try {
    session = await BrowserInterfaceSession.open({ definition: content.definition, plan: emptyPlan, policy: content.policy, confirmation, evidenceRoot: root })
    for (let index = 0; index < request.max_iterations; index++) {
      await authorized(client, request)
      const observation = observed(session, request)
      const input = { id: randomUUID(), previous_id: lastTurnId, observation, evidence_digest: session.evidence.previous }
      await session.evidence.write(`turn-${index}.request.json`, Buffer.from(canonical(input)))
      const turn = await client.call("turns", input)
      lastTurnId = input.id
      await session.evidence.write(`turn-${index}.proposal.json`, Buffer.from(canonical(turn)))
      if (turn.id !== input.id || turn.state !== "generated" || turn.previous_id !== input.previous_id || canonical(turn.input) !== canonical({ observation, evidence_digest: input.evidence_digest }))
        throw new Error("The saved model turn is unresolved or failed; do not repeat an action")
      const proposal = validateProposal(turn.proposal, request.spec, observation)
      if (digest(proposal) !== turn.candidate_digest)
        throw new Error("Model proposal digest changed")
      await authorized(client, request)
      await session.observe()
      if (canonical(observed(session, request)) !== canonical(observation))
        throw new Error("Interface changed while Aira was considering the next action")
      if (proposal.kind !== "act") {
        result = proposal.kind === "finish" ? "client_reported_success" : "needs_information"
        await session.evidence.append("exploration_result", { result, proposal, hardware_qualified: false })
        break
      }
      // Re-observe immediately before selecting the already approved action. Stale data stops.
      let after = null
      let outcome = "uncertain"
      try {
        await session.step(digest(session.lastObservation), proposal.action_index)
        after = observed(session, request)
        outcome = "executed"
      }
      finally {
        const report = { proposal_digest: turn.candidate_digest, outcome, before_digest: digest(observation), after, evidence_digest: session.evidence.previous }
        shape("report", report)
        await session.evidence.write(`turn-${index}.report.json`, Buffer.from(canonical({ turn_id: turn.id, report })))
        await client.call("report", { report }, turn.id)
      }
      if (index === request.max_iterations - 1)
        result = "budget_exhausted"
    }
    await client.call("end", { last_turn_id: lastTurnId, reason: result === "client_reported_success" ? "client_finished" : "client_stopped" })
    return { state: result, evidence: session.evidence.directory, hardware_qualified: false }
  }
  finally {
    await session?.close()
  }
}

export async function syncExploration(path, { client = null } = {}) {
  const content = await readRequest(path)
  client ??= new InterfaceClient(content)
  const root = dirname(path)
  let synced = 0
  // Recovery sends only saved immutable reports; it never opens a browser or asks a model.
  for (const name of (await readdir(root)).filter(name => /^interface-[A-Za-z0-9]+$/.test(name))) {
    const directory = join(root, name)
    if (!(await lstat(directory)).isDirectory() || (await lstat(directory)).isSymbolicLink())
      throw new Error("Invalid saved evidence directory")
    for (const reportName of (await readdir(directory)).filter(name => /^turn-\d+\.report\.json$/.test(name)).sort()) {
      const saved = JSON.parse(await readPrivateSelection(join(directory, reportName), 262144))
      shape("report", saved.report)
      await client.call("report", { report: saved.report }, saved.turn_id)
      synced += 1
    }
  }
  return { synced_reports: synced, session: await client.call("status"), browser_opened: false }
}

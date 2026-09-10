import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { lstat, realpath } from "node:fs/promises"
import { dirname, join } from "node:path"
import { metadataFields, selectionShape, validateApplicationAnalysis, validateApplicationCandidates } from "./application-selection-contract.mjs"
import { canonical, checkInteger, checkObject, digest } from "./contract.mjs"
import { Evidence, readPrivateSelection } from "./evidence.mjs"
import { nativeDiscoveryResult } from "./native-discovery.mjs"
import { nativeCall } from "./native-transport.mjs"

export function selectedMetadata(inventory, indices, id) {
  if (!Array.isArray(indices) || !indices.length || indices.length > 10 || new Set(indices).size !== indices.length)
    throw new Error("Explicitly select one to ten unique candidate numbers")
  const candidates = indices.map((index) => {
    checkInteger(index, 1, inventory.applications.length)
    const item = inventory.applications[index - 1]
    return { id: `candidate_${index}`, ...Object.fromEntries([...metadataFields, "info_sha256"].map(field => [field, item.declared?.[field] ?? null])) }
  })
  return validateApplicationCandidates({ schema: "airalogy.application-candidates.v1", id, source_digest: digest(inventory), scope: "explicitly_selected_metadata_only", candidates })
}

export async function prepareApplicationSelection({ requestFile, indices, workspace }) {
  const { report: inventory } = await nativeDiscoveryResult(requestFile)
  const report = selectedMetadata(inventory, indices, randomUUID())
  const preview = { schema: "airalogy.application-selection-local.v1", discovery_request: requestFile, indices, report, report_digest: digest(report), applications_opened: false, uploaded: false }
  const evidence = await Evidence.create(workspace, preview)
  await evidence.write("selection.json", Buffer.from(canonical(preview)))
  await evidence.write("candidates.json", Buffer.from(canonical(report)))
  return { selection_file: join(evidence.directory, "selection.json"), candidates_file: join(evidence.directory, "candidates.json"), capture_digest: digest(report), applications_opened: false, model_called: false, uploaded: false }
}

async function privateJSON(path) {
  if (await realpath(dirname(path)) !== dirname(path))
    throw new Error("Use a canonical private selection directory")
  for (const selected of [path, dirname(path)]) {
    const info = await lstat(selected)
    if (info.isSymbolicLink() || info.uid !== process.getuid() || (info.mode & 0o077) || (selected === path ? !info.isFile() || info.nlink !== 1 : !info.isDirectory()))
      throw new Error("Selection artifacts must remain owner-only and unlinked")
  }
  return JSON.parse(await readPrivateSelection(path))
}

export async function resolveApplicationSelection({ selectionFile, candidateId, analysisFile, buildFile }) {
  if (join(dirname(selectionFile), "selection.json") !== selectionFile)
    throw new Error("Select the original private selection file")
  const saved = await privateJSON(selectionFile)
  checkObject(saved, ["schema", "discovery_request", "indices", "report", "report_digest", "applications_opened", "uploaded"])
  if (saved.schema !== "airalogy.application-selection-local.v1" || saved.applications_opened !== false || saved.uploaded !== false || saved.report_digest !== digest(saved.report))
    throw new Error("Private selection changed")
  const { report: inventory } = await nativeDiscoveryResult(saved.discovery_request)
  if (canonical(selectedMetadata(inventory, saved.indices, saved.report.id)) !== canonical(saved.report) || canonical(await privateJSON(join(dirname(selectionFile), "candidates.json"))) !== canonical(saved.report))
    throw new Error("Discovery evidence or selected metadata changed")
  const candidate = saved.report.candidates.find(item => item.id === candidateId)
  if (!candidate?.info_sha256)
    throw new Error("Select a known candidate with readable metadata before inspecting identity")
  let analysisDigest = null
  if (analysisFile) {
    const exported = selectionShape("export", await privateJSON(analysisFile))
    if (exported.capture_digest !== saved.report_digest)
      throw new Error("Analysis belongs to different selected metadata")
    validateApplicationAnalysis(exported.analysis, saved.report)
    if (!exported.analysis.recommendations.some(item => item.candidate_id === candidateId))
      throw new Error("The explicitly selected candidate was not recommended; use manual selection separately")
    analysisDigest = digest(exported)
  }
  // Candidate numbers map only through original private evidence, never a
  // model-supplied path. Current code identity is checked independently.
  const original = inventory.applications[Number(candidateId.slice("candidate_".length)) - 1]
  const inspection = await nativeCall(buildFile, { operation: "inspect_application", bundle_path: original.bundle_path })
  if (inspection.bundle.info_sha256 !== candidate.info_sha256)
    throw new Error("Application metadata changed; discover and review a new snapshot")
  return { candidate_id: candidateId, capture_digest: saved.report_digest, analysis_digest: analysisDigest, inspection, applications_opened: false, ui_actions_approved: false, hardware_qualified: false }
}

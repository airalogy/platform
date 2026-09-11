import { Buffer } from "node:buffer"
import { lstat, open } from "node:fs/promises"
import { basename, dirname, join } from "node:path"
import { canonical, checkObject, digest } from "./contract.mjs"
import { Evidence, readPrivateSelection, syncDirectory } from "./evidence.mjs"
import { validateNativeSelection } from "./native-contract.mjs"
import { previewSurvey, runSurvey, validateSurveySelection } from "./survey.mjs"
import { assembleSurveyDefinition, surveyShape, validateSurveyReport } from "./survey-contract.mjs"

async function readPrivateBytes(path) {
  const info = await lstat(path)
  const parent = await lstat(dirname(path))
  if (process.platform === "win32" || !info.isFile() || info.isSymbolicLink() || info.nlink !== 1 || (info.mode & 0o077) || info.uid !== process.getuid() || !parent.isDirectory() || parent.isSymbolicLink() || parent.uid !== process.getuid() || (parent.mode & 0o077))
    throw new Error("Survey workspaces require owner-only POSIX files and directories")
  return readPrivateSelection(path)
}

async function readPrivateJson(path) {
  return JSON.parse(await readPrivateBytes(path))
}

export async function prepareSurvey(selection, workspace) {
  const preview = await previewSurvey(selection)
  const evidence = await Evidence.create(workspace, preview)
  await evidence.write("request.json", Buffer.from(canonical({ selection: preview.definition, preview_digest: preview.sha256 })))
  return { request_file: join(evidence.directory, "request.json"), local_preview_digest: preview.sha256, browser_opened: false, model_called: false }
}

async function readRequest(path, options = {}) {
  const request = await readPrivateJson(path)
  checkObject(request, ["selection", "preview_digest"])
  const preview = await previewSurvey(request.selection, options)
  if (preview.sha256 !== request.preview_digest)
    throw new Error("Survey target, runtime or capture policy changed; prepare and review again")
  return { request, preview }
}

export async function runPreparedSurvey(path, confirmation) {
  const { request, preview } = await readRequest(path)
  if (confirmation !== preview.sha256)
    throw new Error("Confirm the reviewed local survey digest before opening software")
  const root = dirname(path)
  // Launch itself may initialize hardware. Retain this before any browser work;
  // an uncertain run must never be replayed through a retry of this request.
  const marker = await open(join(root, "run.started"), "wx", 0o600)
  try {
    await marker.writeFile(preview.sha256)
    await marker.sync()
  }
  finally { await marker.close() }
  await syncDirectory(root)
  const result = await runSurvey(request.selection, { confirmation, evidenceRoot: root })
  const evidence = new Evidence(root)
  await evidence.write("result.json", Buffer.from(canonical(result)))
  await evidence.write("manual-analysis.json", Buffer.from(canonical({
    capture_digest: result.report_digest,
    analysis: { summary: "Review this observation before choosing readbacks and a visible identity anchor.", features: [], read_controls: [], identity_control: null, route: "unknown", limitations: ["Single unqualified observation; no actions or physical state tested."], missing_information: [] },
  })))
  return { ...result, manual_analysis_file: join(root, "manual-analysis.json"), model_called: false }
}

async function savedPreparation(path) {
  // Reading history must not inspect current software, run a helper or relaunch a
  // target. Live execution independently revalidates all source/runtime pins.
  const request = await readPrivateJson(path)
  checkObject(request, ["selection", "preview_digest"])
  const preview = await readPrivateJson(join(dirname(path), "preview.json"))
  checkObject(preview, ["schema", "engine", "definition", "sha256"])
  const { sha256, ...payload } = preview
  if (preview.schema !== "airalogy.interface-survey-preview.v1" || digest(payload) !== sha256 || request.preview_digest !== sha256 || canonical(request.selection) !== canonical(preview.definition))
    throw new Error("Saved survey preparation changed")
  if (request.selection.schema === "airalogy.native-survey-selection.v1")
    validateNativeSelection(request.selection)
  else
    validateSurveySelection(request.selection)
  return { request, preview }
}

async function exists(path) {
  try {
    await lstat(path)
    return true
  }
  catch (error) {
    if (error.code === "ENOENT")
      return false
    throw error
  }
}

export async function inspectPreparedSurvey(path) {
  const { request, preview } = await savedPreparation(path)
  const root = dirname(path)
  const base = { request_file: path, local_preview_digest: preview.sha256, application_opened: false, model_called: false, hardware_qualified: false }
  if (!await exists(join(root, "run.started"))) {
    if (await exists(join(root, "result.json")))
      throw new Error("Saved result has no matching launch marker")
    return { ...base, state: "prepared" }
  }
  if ((await readPrivateBytes(join(root, "run.started"))).toString("utf8") !== preview.sha256)
    throw new Error("The saved survey launch does not match this preparation")
  if (!await exists(join(root, "result.json")))
    return { ...base, state: "observation_unresolved", retry_allowed: false }
  const result = await readPrivateJson(join(root, "result.json"))
  checkObject(result, ["evidence", "report_file", "report_digest", "actions_executed", "hardware_qualified"])
  if (dirname(result.evidence) !== root || !/^interface-[A-Za-z0-9]+$/.test(basename(result.evidence)) || result.report_file !== join(result.evidence, "survey.json") || result.actions_executed !== 0 || result.hardware_qualified !== false)
    throw new Error("Use only this preparation's retained capture result")
  const report = validateSurveyReport(await readPrivateJson(result.report_file))
  if (digest(report) !== result.report_digest)
    throw new Error("The saved survey report changed")
  const target = { application: request.selection.target.application, version: request.selection.target.version, title: request.selection.target.title, locale: request.selection.target.locale, kind: request.selection.target.source.kind }
  if (report.preview_digest !== preview.sha256 || canonical(report.target) !== canonical(target) || report.capture_values !== request.selection.capture_values)
    throw new Error("Saved report no longer matches this preparation")
  return { ...base, state: "snapshot_saved", capture_digest: result.report_digest, report_file: result.report_file, controls_count: report.controls.length, retry_allowed: false }
}

export async function readPreparedSurvey(path) {
  const status = await inspectPreparedSurvey(path)
  if (status.state !== "snapshot_saved")
    throw new Error("A complete retained observation is required; do not replay an uncertain launch")
  const { request, preview } = await savedPreparation(path)
  const report = validateSurveyReport(await readPrivateJson(status.report_file))
  if (preview.sha256 !== status.local_preview_digest || digest(report) !== status.capture_digest)
    throw new Error("Saved survey changed during review")
  return { request, preview, report, status }
}

export async function assemblePreparedSurvey(path, analysisPath, workspace) {
  const supplied = await readPrivateJson(analysisPath)
  return assembleReviewedSurvey(path, supplied, workspace)
}

export async function assembleReviewedSurvey(path, supplied, workspace) {
  const { request, preview, report, status } = await readPreparedSurvey(path)
  let origin
  if (supplied.schema === "airalogy.survey-analysis-export.v1") {
    surveyShape("export", supplied)
    origin = { kind: "aira_client_supplied_export", session_id: supplied.session_id, turn_id: supplied.turn_id }
  }
  else {
    checkObject(supplied, ["capture_digest", "analysis"])
    origin = { kind: "manual" }
  }
  if (supplied.capture_digest !== status.capture_digest)
    throw new Error("Analysis must refer to this exact capture, not another or edited report")
  const draft = assembleSurveyDefinition(request.selection, report, supplied.analysis, preview.sha256)
  const evidence = await Evidence.create(workspace, { schema: "airalogy.survey-assembly.v1", ...draft.provenance, local_preview_digest: preview.sha256, origin })
  await evidence.write("definition.json", Buffer.from(canonical(draft.definition)))
  await evidence.write("plan.json", Buffer.from(canonical(draft.plan)))
  await evidence.write("analysis.json", Buffer.from(canonical(supplied)))
  await evidence.write("survey.json", Buffer.from(canonical(report)))
  return { definition_file: join(evidence.directory, "definition.json"), plan_file: join(evidence.directory, "plan.json"), provenance_file: join(evidence.directory, "preview.json"), browser_opened: false, model_called: false, actions_approved: false, hardware_qualified: false }
}

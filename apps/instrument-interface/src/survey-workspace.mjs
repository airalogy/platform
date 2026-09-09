import { Buffer } from "node:buffer"
import { lstat, open } from "node:fs/promises"
import { basename, dirname, join } from "node:path"
import { canonical, checkObject, digest } from "./contract.mjs"
import { Evidence, readPrivateSelection, syncDirectory } from "./evidence.mjs"
import { previewSurvey, runSurvey } from "./survey.mjs"
import { assembleSurveyDefinition, surveyShape, validateSurveyReport } from "./survey-contract.mjs"

async function readPrivateJson(path) {
  const info = await lstat(path)
  const parent = await lstat(dirname(path))
  if (process.platform === "win32" || !info.isFile() || info.isSymbolicLink() || info.nlink !== 1 || (info.mode & 0o077) || info.uid !== process.getuid() || !parent.isDirectory() || parent.isSymbolicLink() || parent.uid !== process.getuid() || (parent.mode & 0o077))
    throw new Error("Survey workspaces require owner-only POSIX files and directories")
  return JSON.parse(await readPrivateSelection(path))
}

export async function prepareSurvey(selection, workspace) {
  const preview = await previewSurvey(selection)
  const evidence = await Evidence.create(workspace, preview)
  await evidence.write("request.json", Buffer.from(canonical({ selection: preview.definition, preview_digest: preview.sha256 })))
  return { request_file: join(evidence.directory, "request.json"), local_preview_digest: preview.sha256, browser_opened: false, model_called: false }
}

async function readRequest(path) {
  const request = await readPrivateJson(path)
  checkObject(request, ["selection", "preview_digest"])
  const preview = await previewSurvey(request.selection)
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

export async function assemblePreparedSurvey(path, analysisPath, workspace) {
  const { request, preview } = await readRequest(path)
  const root = dirname(path)
  if ((await readPrivateSelection(join(root, "run.started"))).toString("utf8") !== preview.sha256)
    throw new Error("The saved survey launch does not match this preparation")
  const result = await readPrivateJson(join(root, "result.json"))
  checkObject(result, ["evidence", "report_file", "report_digest", "actions_executed", "hardware_qualified"])
  if (dirname(result.evidence) !== root || !/^interface-[A-Za-z0-9]+$/.test(basename(result.evidence)) || result.report_file !== join(result.evidence, "survey.json") || result.actions_executed !== 0 || result.hardware_qualified !== false)
    throw new Error("Use only this preparation's retained capture result")
  const report = validateSurveyReport(await readPrivateJson(result.report_file))
  if (digest(report) !== result.report_digest)
    throw new Error("The saved survey report changed")
  const supplied = await readPrivateJson(analysisPath)
  let origin
  if (supplied.schema === "airalogy.survey-analysis-export.v1") {
    surveyShape("export", supplied)
    origin = { kind: "aira_client_supplied_export", session_id: supplied.session_id, turn_id: supplied.turn_id }
  }
  else {
    checkObject(supplied, ["capture_digest", "analysis"])
    origin = { kind: "manual" }
  }
  if (supplied.capture_digest !== result.report_digest)
    throw new Error("Analysis must refer to this exact capture, not another or edited report")
  const draft = assembleSurveyDefinition(request.selection, report, supplied.analysis, preview.sha256)
  const evidence = await Evidence.create(workspace, { schema: "airalogy.survey-assembly.v1", ...draft.provenance, local_preview_digest: preview.sha256, origin })
  await evidence.write("definition.json", Buffer.from(canonical(draft.definition)))
  await evidence.write("plan.json", Buffer.from(canonical(draft.plan)))
  await evidence.write("analysis.json", Buffer.from(canonical(supplied)))
  await evidence.write("survey.json", Buffer.from(canonical(report)))
  return { definition_file: join(evidence.directory, "definition.json"), plan_file: join(evidence.directory, "plan.json"), provenance_file: join(evidence.directory, "preview.json"), browser_opened: false, model_called: false, actions_approved: false, hardware_qualified: false }
}

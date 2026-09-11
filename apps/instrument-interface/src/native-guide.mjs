import { Buffer } from "node:buffer"
import { realpath } from "node:fs/promises"
import { isAbsolute, join, relative } from "node:path"
import { prepareApplicationSelection, resolveApplicationSelection } from "./application-selection.mjs"
import { canonical, checkObject, checkText, digest } from "./contract.mjs"
import { Evidence, readPrivateSelection } from "./evidence.mjs"
import { validateNativePin } from "./native-contract.mjs"
import { nativeDiscoveryResult } from "./native-discovery.mjs"
import { prepareNativeLaunch, runNativeLaunch } from "./native-launch.mjs"
import { selectNative } from "./native-survey.mjs"
import { nativeCall, nativeFailureCode, validateNativeBuild } from "./native-transport.mjs"
import { chooseNumbers, reviewSurvey, terminalJson } from "./survey-review.mjs"
import { prepareSurvey, runPreparedSurvey } from "./survey-workspace.mjs"

const backend = Object.freeze({ nativeDiscoveryResult, validateNativeBuild, prepareApplicationSelection, resolveApplicationSelection, prepareNativeLaunch, runNativeLaunch, nativeCall, selectNative, prepareSurvey, runPreparedSurvey, reviewSurvey })

class GuideCancelled extends Error {}

// The injected backend is a trusted-code test seam, never a CLI/JSON/remote tool
// registry. Production binds these exact existing, independently gated operations.
export async function guideNative(options, terminal, operations = backend) {
  checkObject(options, ["requestFile", "buildFile", "workspace", "locale", "redactIdentifiers"])
  checkText(options.locale)
  if (!Array.isArray(options.redactIdentifiers) || options.redactIdentifiers.length > 32 || new Set(options.redactIdentifiers).size !== options.redactIdentifiers.length)
    throw new Error("Choose at most 32 exact private-region identifiers")
  options.redactIdentifiers.forEach(value => checkText(value))
  const guard = () => terminal.signal?.throwIfAborted()
  guard()
  const { report } = await operations.nativeDiscoveryResult(options.requestFile)
  guard()
  const { manifest } = await operations.validateNativeBuild(options.buildFile)
  guard()
  // Do not create evidence inside the inspected application directory, including
  // a vendor bundle, even if the caller selected a writable output path.
  const workspace = await realpath(options.workspace)
  const distance = relative(report.directory.path, workspace)
  if (!isAbsolute(options.workspace) || workspace.split("/").some(part => part.toLowerCase().endsWith(".app")) || (distance !== ".." && !distance.startsWith("../")))
    throw new Error("Use an existing private workspace outside the discovered application directory")
  const buildDigest = digest(manifest)
  const preview = { schema: "airalogy.native-guide.v1", discovery_request: options.requestFile, discovery_digest: digest(report), build_file: options.buildFile, build_digest: buildDigest, locale: options.locale, redact_identifiers: options.redactIdentifiers, capture_values: false, model_called: false, hardware_qualified: false }
  const evidence = await Evidence.create(options.workspace, preview)
  const recovery = { guide_directory: evidence.directory, discovery_request: options.requestFile }
  let stage = "select_application"
  const write = value => terminal.write(value)
  const ask = async (prompt) => {
    guard()
    const answer = await terminal.question(prompt)
    guard()
    if (answer === "")
      throw new GuideCancelled("Operator declined")
    return answer
  }
  const confirm = async (scope, prompt, prefix = "") => {
    const sha256 = digest(scope)
    write(`${terminalJson(scope)}\n${prompt}\n${prefix}${sha256}\n`)
    if (await ask("Type the complete confirmation above; anything else stops / 输入上方完整确认文字，其他输入停止： ") !== `${prefix}${sha256}`)
      throw new GuideCancelled("Operator did not confirm")
    return sha256
  }
  const checkBuild = async () => {
    guard()
    if (digest((await operations.validateNativeBuild(options.buildFile)).manifest) !== buildDigest)
      throw new Error("Guide build changed")
    guard()
  }
  const checkpoint = async (name, details) => {
    stage = name
    await evidence.append("stage_prepared", { stage, ...details })
  }
  const save = (name, value) => evidence.write(name, Buffer.from(canonical(value)))
  write(`Private guide / 私有引导目录：${terminalJson(evidence.directory)}\n`)
  write("This is a NEW local onboarding, not recovery of an uncertain launch. Keep all original receipts. No AI, hardware qualification, UI writes or installation. / 这是一次新的本地接入，不是启动不确定状态的恢复。保留原回执；不调用 AI、不授予实机资格、不写界面、不安装适配包。\n")
  try {
    write(`Historical discovery / 历史发现范围：${terminalJson({ directory: report.directory, stopped_reason: report.stopped_reason, skipped: report.skipped })}\n`)
    report.applications.forEach((item, index) => write(`${index + 1}. ${terminalJson(item)}\n`))
    const selectedId = chooseNumbers(await ask("Choose one application number / 选择一个应用序号： "), report.applications.map((_, index) => ({ id: index + 1 })))[0]
    const candidate = report.applications[selectedId - 1]
    if (candidate.metadata_status !== "read" || !candidate.declared?.info_sha256)
      throw new Error("Selected application metadata is unavailable")
    const selected = await operations.prepareApplicationSelection({ requestFile: options.requestFile, indices: [selectedId], workspace: evidence.directory })
    recovery.selection_file = selected.selection_file
    const inspectionScope = { operation: "inspect_selected_application", candidate, build_file: options.buildFile, build_digest: buildDigest, discovery_digest: preview.discovery_digest, applications_opened: false, ui_observed: false }
    await checkpoint("inspect_application", { selection: selected, scope: inspectionScope })
    await confirm(inspectionScope, "Confirm selected code/process metadata inspection / 确认仅检查选定应用的代码与进程元数据")
    await checkBuild()
    const resolved = await operations.resolveApplicationSelection({ selectionFile: selected.selection_file, candidateId: `candidate_${selectedId}`, buildFile: options.buildFile })
    const inspection = resolved.inspection
    if (inspection.unresolved_instances !== 0 || !Array.isArray(inspection.running) || inspection.running.length > 8 || inspection.bundle.info_sha256 !== candidate.declared.info_sha256 || inspection.bundle.bundle_path !== candidate.bundle_path)
      throw new Error("Reconcile conflicting or changed application instances before continuing")
    await save("inspection.json", resolved)
    let pin
    if (inspection.running.length === 0) {
      stage = "prepare_launch"
      const reason = await ask("Software is not running. State your authorized reason for initialization, or leave blank to stop / 软件未运行。填写获准启动及初始化的理由，留空停止： ")
      checkText(reason, 2000)
      await checkBuild()
      const launch = await operations.prepareNativeLaunch({ buildFile: options.buildFile, bundlePath: candidate.bundle_path, workspace: evidence.directory, reason })
      recovery.launch_request = launch.request_file
      await checkpoint("launch_application", { launch })
      const scope = JSON.parse(await readPrivateSelection(launch.preview_file))
      if (canonical(scope.bundle) !== canonical(inspection.bundle) || digest(scope) !== launch.preview_digest)
        throw new Error("Selected software changed before launch review")
      const confirmation = await confirm(scope, "Opening software can initialize equipment and access the network. Independent local authority is required; it is NOT a read-only action. / 打开软件可能初始化设备并访问网络，必须已有独立现场授权，不是只读操作。", "INITIALIZE ")
      await checkBuild()
      const launched = await operations.runNativeLaunch(launch.request_file, { confirmation, acknowledgeInitialization: true })
      pin = launched.pin
      await save("launch-receipt.json", launched)
    }
    else {
      inspection.running.forEach((item, index) => write(`${index + 1}. ${terminalJson(item.process)}\n`))
      const processIndex = chooseNumbers(await ask("Choose the exact existing process / 选择准确的已有进程序号： "), inspection.running.map((_, index) => ({ id: index })))[0]
      pin = inspection.running[processIndex]
    }
    validateNativePin(pin)
    if (canonical(pin.bundle) !== canonical(inspection.bundle))
      throw new Error("Application identity changed")
    const windowScope = { operation: "inspect_windows", pin, build_file: options.buildFile, build_digest: buildDigest, capture: "window titles/roles/geometry flags only", screenshots: false, values: false, actions: false }
    await checkpoint("inspect_windows", { scope: windowScope })
    await confirm(windowScope, "Confirm reading window metadata from this exact process / 确认只读取这个准确进程的窗口元数据")
    await checkBuild()
    const windows = await operations.nativeCall(options.buildFile, { operation: "inspect_windows", pin })
    await save("windows.json", windows)
    write(`${terminalJson(windows)}\n`)
    // The shared capture backend requires one measurable selected window. Do not
    // silently choose another window, close dialogs, foreground or repair the UI.
    if (windows.windows?.length !== 1 || windows.windows[0].role !== "AXWindow" || windows.windows[0].minimized !== false || windows.windows[0].has_geometry !== true || !windows.windows[0].title)
      throw new Error("Operator must reconcile missing, extra, hidden or unsupported windows")
    const title = windows.windows[0].title
    await checkBuild()
    const selection = await operations.selectNative({ buildFile: options.buildFile, bundlePath: pin.bundle.bundle_path, pid: pin.process.pid, title, locale: options.locale, captureValues: false, redactIdentifiers: options.redactIdentifiers })
    if (canonical(selection.target.source.pin) !== canonical(pin))
      throw new Error("Selected process lifetime changed")
    const prepared = await operations.prepareSurvey(selection, evidence.directory)
    recovery.survey_request = prepared.request_file
    await checkpoint("capture_interface", { prepared })
    const surveyPreview = JSON.parse(await readPrivateSelection(join(prepared.request_file, "..", "preview.json")))
    const { sha256, ...surveyScope } = surveyPreview
    if (sha256 !== prepared.local_preview_digest || digest(surveyScope) !== sha256)
      throw new Error("Survey preview changed")
    const confirmation = await confirm(surveyScope, "Confirm one scoped interface observation. Static text may be confidential; values/screenshots/actions are off. / 确认一次限定界面观察。静态文字可能含机密；不采集输入值、不截图、不操作控件。")
    await checkBuild()
    const captured = await operations.runPreparedSurvey(prepared.request_file, confirmation)
    recovery.report_file = captured.report_file
    await save("capture-receipt.json", captured)
    stage = "review_readbacks"
    guard()
    const draft = await operations.reviewSurvey(prepared.request_file, evidence.directory, { ...terminal, question: ask })
    const result = { state: "draft_created", ...recovery, draft, application_not_closed_by_guide: true, current_process_state: "not_checked_after_capture", model_called: false, hardware_qualified: false, installation_approved: false }
    await save("guide-result.json", result)
    return result
  }
  catch (error) {
    const nextStep = {
      select_application: "Review saved metadata and select one readable candidate. / 检查历史元数据，明确选择一个可读取的候选。",
      inspect_application: "Check the selection and current signed application identity; no startup was authorized. / 核对选择与当前应用身份；此阶段未授权启动。",
      prepare_launch: "Obtain independent startup/initialization authorization before preparing a launch. / 准备启动前，先取得独立的软件启动及设备初始化授权。",
      launch_application: "Read launch-status for the saved launch_request; do not relaunch after uncertainty. / 使用原 launch_request 查看 launch-status，不确定时不得重新启动。",
      inspect_windows: "Reconcile the exact process, session and windows with the operator; the guide cannot close dialogs or change focus. / 与操作者核对准确进程、会话及窗口；引导不会关闭弹窗或改变焦点。",
      capture_interface: "Read survey status for survey_request; never delete its start marker or replay it. / 使用原 survey_request 查看观察状态，不得删除启动标记或重放。",
      review_readbacks: "Use survey review with the saved survey_request; inspect existing output before saving another draft. / 对原 survey_request 继续审核，再次保存草稿前检查已有输出。",
    }[stage]
    const reason = error instanceof GuideCancelled || terminal.signal?.aborted ? "operator_cancelled" : nativeFailureCode(error)
    const result = { state: "needs_attention", stage, reason, next_step: nextStep, ...recovery, automatic_retry: false, application_not_closed_by_guide: true, physical_safe_stop_confirmed: false, model_called: false, hardware_qualified: false, installation_approved: false }
    await save("guide-stopped.json", result)
    write("Stopped. Do not rerun this guide as recovery. Use the saved launch-status, survey status or review request as appropriate; no app was closed or physical stop confirmed. / 已停止。不要重跑引导来恢复；使用保存的启动状态、观察状态或审核请求核对。未关闭应用，也未确认物理停止。\n")
    write(`${nextStep}\n`)
    return result
  }
}

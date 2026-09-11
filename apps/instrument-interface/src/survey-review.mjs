import { Buffer } from "node:buffer"
import { lstat, realpath } from "node:fs/promises"
import { dirname, isAbsolute, join } from "node:path"
import { canonical, checkObject, digest } from "./contract.mjs"
import { Evidence } from "./evidence.mjs"
import { assembleSurveyDefinition, validateSurveyReport } from "./survey-contract.mjs"
import { assembleReviewedSurvey, readPreparedSurvey } from "./survey-workspace.mjs"

// Labels and readbacks are untrusted, including terminal escape/bidi controls.
// Quote rather than truncate: an omitted suffix could hide the selected identity.
export function terminalJson(value) {
  return JSON.stringify(value, null, 2).replace(/[\u007F-\u009F\u061C\u200E\u200F\u2028-\u202E\u2066-\u2069]/g, character => `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`)
}

export function surveyChoices(report) {
  validateSurveyReport(report)
  const reads = report.controls.filter(control => control.locator && control.read)
  const identities = reads.filter(control => control.read === "text" && control.value.trim() && Buffer.byteLength(control.value) <= 512)
  return { reads, identities }
}

export function chooseNumbers(answer, options, { multiple = false } = {}) {
  if (typeof answer !== "string" || answer.length > 128 || !(multiple ? /^\d+(?:,\d+)*$/ : /^\d+$/).test(answer))
    throw new Error("Choose explicit one-based numbers without ranges or defaults")
  const numbers = answer.split(",").map(Number)
  if (numbers.length > (multiple ? 16 : 1) || new Set(numbers).size !== numbers.length || numbers.some(number => !Number.isSafeInteger(number) || number < 1 || number > options.length))
    throw new Error("Choose distinct available controls (at most 16 readbacks)")
  return numbers.map(number => options[number - 1].id)
}

export async function previewManualSurvey(path, choices, workspace) {
  checkObject(choices, ["identity_control", "read_controls"])
  const { request, preview, report, status } = await readPreparedSurvey(path)
  if (process.platform === "win32" || !isAbsolute(workspace))
    throw new Error("Choose an existing private POSIX output directory")
  const info = await lstat(workspace)
  if (!info.isDirectory() || info.isSymbolicLink() || (info.mode & 0o077) || info.uid !== process.getuid())
    throw new Error("Choose an owner-only output directory (0700)")
  const supplied = {
    capture_digest: status.capture_digest,
    analysis: {
      summary: "Manually reviewed observed identity and readbacks; no actions or physical state validated.",
      features: [],
      ...choices,
      route: report.target.kind === "native_macos" ? "native_accessibility" : "browser",
      limitations: ["Historical observation, not current software availability, physical safety or experimental success. Reopening needs separate authorization."],
      missing_information: [],
    },
  }
  const draft = assembleSurveyDefinition(request.selection, report, supplied.analysis, preview.sha256)
  const selected = new Set([choices.identity_control, ...choices.read_controls])
  const value = {
    schema: "airalogy.survey-manual-review.v1",
    request_file: path,
    local_preview_digest: preview.sha256,
    workspace: { path: await realpath(workspace), device: info.dev, inode: info.ino },
    supplied,
    observed_controls: report.controls.filter(control => selected.has(control.id)),
    draft,
    application_opened: false,
    model_called: false,
    actions_approved: false,
    hardware_qualified: false,
  }
  return { ...value, sha256: digest(value) }
}

export async function confirmManualSurvey(path, choices, workspace, confirmation) {
  const preview = await previewManualSurvey(path, choices, workspace)
  if (confirmation !== preview.sha256)
    throw new Error("Review the exact current capture, fields and output directory before confirming")
  const result = await assembleReviewedSurvey(path, preview.supplied, preview.workspace.path)
  const root = dirname(result.definition_file)
  await new Evidence(root).write("manual-review.json", Buffer.from(canonical(preview)))
  return { ...result, review_file: join(root, "manual-review.json"), review_digest: preview.sha256 }
}

// Inject only terminal I/O for tests, never an execution backend. This flow has no
// path to observe software, acquire credentials, call a model or perform actions.
export async function reviewSurvey(path, workspace, { question, write }) {
  const { report } = await readPreparedSurvey(path)
  const options = surveyChoices(report)
  if (!options.identities.length || !options.reads.length)
    throw new Error("No observed unique text identity/readbacks. Narrow and separately authorize a new observation; do not invent locators")
  write("PRIVATE LOCAL REVIEW / 本地私有审核：以下为历史观察，不是实时状态。\nNo software/model will be opened. No writes to equipment. / 不打开软件、不调用模型、不操作设备。\n")
  write(`Observed application / 已观察软件：${terminalJson(report.target)}\n`)
  write("Choose the actual visible software/version identity, not a result or status. / 选择软件与版本标识，不要选择结果或运行状态。\n")
  const show = controls => controls.forEach((control, index) => write(`${index + 1}. ${terminalJson(control.label)} [${terminalJson(control.id)}, ${terminalJson(control.read)}] = ${terminalJson(control.value)}\n`))
  show(options.identities)
  const identity = chooseNumbers(await question("Identity number / 标识序号（无默认值）： "), options.identities)[0]
  write("Choose required readbacks (up to 16); the identity is included automatically. / 选择所需读取字段（至多 16 个），标识自动保留。\n")
  show(options.reads)
  const reads = chooseNumbers(await question("Readback numbers, e.g. 1,3 / 字段序号，如 1,3： "), options.reads, { multiple: true })
  const choices = { identity_control: identity, read_controls: reads }
  const preview = await previewManualSurvey(path, choices, workspace)
  write(`Read-only draft + output scope / 只读草稿与保存范围：\n${terminalJson(preview)}\n`)
  write("This creates a new editable draft, not an installed/qualified adapter. / 将生成新草稿，不会安装或授予设备权限。\n")
  write(`Confirmation SHA-256 / 确认摘要：${preview.sha256}\n`)
  const confirmation = await question("Type the complete sha256 above to save; anything else cancels / 输入上方完整 sha256 保存，其他输入取消： ")
  return confirmManualSurvey(path, choices, workspace, confirmation)
}

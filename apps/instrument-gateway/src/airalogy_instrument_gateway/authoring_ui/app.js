/* Local development only: no remote scripts, device control or automatic run. */
const $ = id => document.getElementById(id)
const token = location.hash.slice(1)
let language = navigator.language.startsWith("zh") ? "zh" : "en"
let busy = false
let currentReview = null
let state = { sessions: [], job: null }
let inspected = null
let firstLoad = true
const uploads = {}
const words = {
  locally_tested_draft: ["Locally tested draft", "本地测试通过的草稿"],
  test_failed: ["Test failed", "测试失败"],
  test_uncertain: ["Test outcome uncertain", "测试结果不确定"],
  not_tested: ["Not tested", "尚未测试"],
  needs_information: ["More information required", "需要补充资料"],
  language: ["Language", "语言"],
  title: ["Local adapter development", "本地适配开发向导"],
  directory: ["Private development directory", "私有开发目录"],
  boundary: ["Development credentials and directory are separate. Approved material may reach your configured external model. Generated code runs only in the isolated, no-network Docker test environment. This guide never starts device software, installs a driver or controls equipment.", "开发目录及凭据独立。已批准资料可能交给实例配置的外部模型。生成代码只在隔离、无网络 Docker 测试环境运行，不启动设备软件、不安装驱动、不控制仪器。"],
  prepare: ["1. Review selected development inputs", "1. 核对选定开发输入"],
  inputHint: ["Select a reviewed specification with the goal, read-only contracts, permitted text materials, independent tests and licenses (128 KiB), plus an independently trusted SDK wheel (64 MiB). Selection copies files locally only. Preview makes no model call. This guide does not invent device contracts or independent expected results, extract PDFs, or download dependencies. Retained-copy quota: 64 files / 256 MiB; preserve files referenced by sessions.", "选择审核过的开发规范：目标、只读契约、获准文本资料、独立测试及许可证（128 KiB），以及独立可信 SDK wheel（64 MiB）。只复制到本地，预览不调用模型。不编造设备契约或独立预期、不提取 PDF、不下载依赖。保留副本配额 64 个 / 256 MiB，请保留会话引用的文件。"],
  spec: ["Reviewed specification JSON", "已审核开发规范 JSON"],
  sdk: ["Trusted SDK wheel", "可信 SDK wheel"],
  digest: ["SDK SHA-256 from an independent trusted source", "来自独立可信来源的 SDK SHA-256"],
  image: ["Preinstalled trusted Docker image digest", "已安装可信 Docker 镜像摘要"],
  calls: ["Maximum model calls", "模型调用次数上限"],
  duration: ["Authorization duration (seconds)", "授权有效时长（秒）"],
  timeout: ["Per-test timeout (seconds)", "单次测试超时（秒）"],
  preview: ["Preview", "预览"],
  work: ["2. Approve, develop and resume", "2. 授权、开发与恢复"],
  handoff: ["Download the PRIVATE authorization. Import it in Platform → Instrument Gateways → Prepare adapter → Develop source. Compare the fingerprint and approve the exact materials and model processing. It contains private material, not a bearer token; never upload request.json. Then return here to confirm the bounded local run.", "下载私有授权文件，在 Platform → 仪器网关 → 准备适配包 → 开发源码中导入。比对指纹，批准准确资料及模型处理。文件含私有资料但不含 bearer 凭据，不要上传 request.json。再回到此处确认有限本地运行。"],
  sessions: ["Saved development session", "已保存开发会话"],
  inspect: ["Inspect saved inputs and results", "查看已保存输入与结果"],
  authorization: ["Download PRIVATE authorization", "下载私有授权文件"],
  run: ["Check approval and preview run", "查询授权并预览运行"],
  pause: ["Pause local development", "暂停本地开发"],
  reconcile: ["Also preview reconciliation of this session's interrupted disposable tests. Only the named containers may be stopped; interruption is recorded as failure, never a pass. This does not stop an instrument.", "同时预览核对本会话中断的隔离测试。只可能停止明确列出的测试容器，中断记录为失败而非通过，不停止仪器。"],
  pauseHint: ["Pause takes effect after the current bounded model/test step and receipt. It does not cancel the Platform grant or stop equipment. Reload never starts work. Old run tickets alone do not prove a process stopped: resume explicitly with the same request/journal. Interrupted tests need separate reconciliation.", "暂停在当前有时限的模型/测试步骤及回执后生效，不撤销平台授权、不停止设备。刷新不启动工作。旧运行记录不证明进程已停止：须用原请求/日志明确恢复，中断测试需单独核对。"],
  privateInputs: ["Private selected inputs and local run history", "私有选定输入及本地运行历史"],
  results: ["3. Review the generated draft", "3. 审核生成的适配草稿"],
  resultHint: ["Validated retained files and client-reported tests are not trusted execution attestations or hardware qualification. Failed/incomplete candidates are not offered as passing packages. Test diagnostics are untrusted data.", "校验过的保留文件及客户端报告的测试，不是可信执行证明或实机资格。失败/未完成候选不作为通过的适配包提供，测试诊断是不可信数据。"],
  next: ["Independently review source, dependencies and confidentiality, then import the draft into Platform and use local setup for separately approved installation. Qualification and startup remain separate. Manual build/test/import remains available without AI.", "独立审核源码、依赖及保密要求，再将草稿导入 Platform，通过本地接入向导进行单独批准的安装。验收、启动仍分别授权，无 AI 时仍可手工构建/测试/导入。"],
  review: ["Review the exact impact", "核对准确影响"],
  confirmHint: ["I reviewed the exact equipment, selected private material, independent tests, SDK/image and limits. I approve only this displayed preparation or development/recovery step, not installation or hardware access.", "我已核对准确设备、私有资料、独立测试、SDK/镜像及限额。只批准本次展示的准备或开发/恢复步骤，不批准安装或硬件访问。"],
  cancel: ["Cancel", "取消"],
  confirm: ["Confirm", "确认"],
  copied: ["Private local copy saved", "已保存私有本地副本"],
  choose: ["Select a saved session", "请选择已保存会话"],
  package: ["Download PRIVATE draft package", "下载私有适配草稿包"],
  report: ["Download PRIVATE test report", "下载私有测试报告"],
  working: ["Checking… No automatic retries.", "正在核对，不自动重试。"],
  failed: ["Operation not confirmed. Check destination, independent inputs, limits/permissions and Platform approval. Preserve the same request and inspect saved status before retrying. Private errors are not exposed here.", "操作尚未确认。请核对位置、独立输入、限额/权限及平台批准，保留原请求，查看已保存状态后再重试。私有错误详情不在此暴露。"],
  session: ["Open the exact private one-hour address printed by this assistant. Restart with the same directory after expiry.", "请打开本向导显示的一小时私有地址；到期后用同一目录重启。"],
  selected: ["Select both input files first.", "请先选择两个输入文件。"],
  alive: ["Local worker observed running", "已观察到本地开发线程正在运行"],
  stopped: ["This guide's local worker finished", "本向导的开发线程已结束"],
  unobserved: ["No live worker observed by this guide; inspect saved history before resuming.", "本向导未观察到活动线程，请先查看历史再决定是否恢复。"],
}
const t = key => words[key][language === "zh" ? 1 : 0]
function translate() {
  document.documentElement.lang = language
  $("language").value = language
  document.querySelectorAll("[data-i18n]").forEach(node => node.textContent = t(node.dataset.i18n))
  $("worker").textContent = t(!state.job ? "unobserved" : state.job.worker_alive ? "alive" : "stopped")
  renderArtifacts()
}
function setBusy(value) {
  busy = value
  document.querySelectorAll("button,input,select").forEach(node => node.disabled = value)
  $("confirm").disabled = value || !$("reviewed").checked
  $("activity").textContent = value ? t("working") : ""
}
async function guarded(action) {
  if (busy)
    return
  setBusy(true)
  $("error").hidden = true
  try {
    await action()
  }
  catch (error) {
    $("error").textContent = error.message
    $("error").hidden = false
  }
  finally { setBusy(false) }
}
async function send(path, body, type = "application/json") {
  if (!/^[\w-]{43}$/.test(token))
    throw new Error(t("session"))
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": type, "X-Airalogy-Setup": token }, body, credentials: "omit", redirect: "error" })
  if (!response.ok)
    throw new Error(t(response.status === 401 ? "session" : "failed"))
  return response
}
const call = async (operation, data = {}) => (await send("/api", JSON.stringify({ operation, data }))).json()
const show = (id, value) => $(id).textContent = JSON.stringify(value, null, 2)
async function refresh() {
  state = await call("state")
  if (firstLoad && state.sessions.length)
    $("new-session").open = false
  firstLoad = false
  $("root").textContent = state.root
  const previous = $("sessions").value
  $("sessions").replaceChildren(new Option(t("choose"), ""), ...state.sessions.map(item => new Option(`${item.goal} · ${item.id}`, item.id)))
  if (state.sessions.some(item => item.id === previous))
    $("sessions").value = previous
  else if (state.sessions.length === 1)
    $("sessions").value = state.sessions[0].id
  show("job", state.job)
  $("worker").textContent = t(!state.job ? "unobserved" : state.job.worker_alive ? "alive" : "stopped")
}
async function download(kind, turnId = null) {
  if (!inspected || inspected.id !== $("sessions").value)
    throw new Error(t("choose"))
  const response = await send("/api", JSON.stringify({ operation: "download", data: { id: inspected.id, kind, turn_id: turnId } }))
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement("a")
  link.href = url
  link.download = kind === "package" ? `private-adapter-${turnId}.zip` : `private-${kind}-${turnId || inspected.id}.json`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
async function inspect() {
  if (!$("sessions").value)
    throw new Error(t("choose"))
  inspected = await call("inspect", { id: $("sessions").value })
  show("inspection", inspected)
  renderArtifacts()
}
function renderArtifacts() {
  $("artifacts").replaceChildren()
  if (!inspected)
    return
  for (const item of inspected.artifacts) {
    const article = document.createElement("article")
    const title = document.createElement("p")
    title.textContent = `${t(item.state)} · ${item.id}`
    article.append(title)
    const summary = document.createElement("p")
    summary.textContent = item.proposal.summary
    article.append(summary)
    for (const question of item.proposal.missing_information) {
      const paragraph = document.createElement("p")
      paragraph.textContent = question
      article.append(paragraph)
    }
    const actions = document.createElement("div")
    actions.className = "row"
    for (const kind of item.state === "locally_tested_draft" ? ["package", "report"] : item.report ? ["report"] : []) {
      const button = document.createElement("button")
      button.textContent = t(kind)
      button.addEventListener("click", () => guarded(() => download(kind, item.id)))
      actions.append(button)
    }
    article.append(actions)
    $("artifacts").append(article)
  }
}
function review(result, operation) {
  currentReview = { result, operation }
  show("impact", result.impact)
  $("reviewed").checked = false
  $("review").showModal()
}
$("language").addEventListener("change", () => {
  language = $("language").value
  translate()
})
document.querySelectorAll("[data-kind]").forEach(input => input.addEventListener("change", () => {
  const kind = input.dataset.kind
  delete uploads[kind]
  $(`${kind}-info`).textContent = ""
  const file = input.files[0]
  if (file) {
    guarded(async () => {
      const result = await (await send(`/upload/${kind}`, file, "application/octet-stream")).json()
      uploads[kind] = result.path
      $(`${kind}-info`).textContent = `${t("copied")}: ${file.name} · ${result.bytes} bytes`
    })
  }
}))
$("prepare-form").addEventListener("submit", (event) => {
  event.preventDefault()
  const data = Object.fromEntries(new FormData(event.currentTarget))
  for (const field of ["max_iterations", "duration_seconds", "timeout_seconds"])
    data[field] = Number(data[field])
  guarded(async () => {
    if (Object.keys(uploads).length !== 2)
      throw new Error(t("selected"))
    review(await call("prepare-preview", { ...data, ...uploads }), "prepare-confirm")
  })
})
$("inspect").addEventListener("click", () => guarded(async () => {
  await refresh()
  await inspect()
}))
$("sessions").addEventListener("change", () => {
  inspected = null
  $("artifacts").replaceChildren()
  $("inspection").textContent = ""
})
$("authorization").addEventListener("click", () => guarded(async () => {
  await inspect()
  await download("authorization")
}))
$("run").addEventListener("click", () => guarded(async () => {
  if (!$("sessions").value)
    throw new Error(t("choose"))
  review(await call("run-preview", { id: $("sessions").value, reconcile: $("reconcile").checked }), "run-confirm")
}))
$("pause").addEventListener("click", () => guarded(async () => {
  if (!state.job || state.job.session_id !== $("sessions").value)
    throw new Error(t("choose"))
  await call("pause", { id: state.job.id })
  await refresh()
}))
$("reviewed").addEventListener("change", () => $("confirm").disabled = busy || !$("reviewed").checked)
$("cancel").addEventListener("click", () => {
  currentReview = null
  $("review").close()
})
$("confirm").addEventListener("click", () => guarded(async () => {
  if (!currentReview || !$("reviewed").checked)
    return
  const { result, operation } = currentReview
  currentReview = null
  $("review").close()
  const outcome = await call(operation, { confirmation: result.confirmation })
  await refresh()
  if (outcome.id) {
    $("sessions").value = outcome.id
    $("new-session").open = false
  }
  await inspect()
}))
// Only poll an observed live worker. Local status cannot start work or call Aira.
setInterval(() => {
  if (!busy && !$("review").open && state.job?.worker_alive) {
    guarded(async () => {
      await refresh()
      if (!state.job?.worker_alive)
        await inspect()
    })
  }
}, 1500)
translate()
guarded(refresh)

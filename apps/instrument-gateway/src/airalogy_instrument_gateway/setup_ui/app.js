/* Local-only UI: no remote scripts, model calls, storage or driver execution. */
const $ = id => document.getElementById(id)
const token = location.hash.slice(1)
let language = navigator.language.startsWith("zh") ? "zh" : "en"
let busy = false
let saved = { requests: [], pairings: [] }
let currentReview = null
const uploads = {}
const words = {
  en: {
    language: "Language",
    title: "Local equipment setup",
    intro: "Pair this workstation, prepare a reviewed installation and return its receipt. This assistant never launches an adapter or controls equipment.",
    boundary: "Local interface only. Pairing, source review, installation, qualification and startup are separate approvals. POSIX / pure-Python installation only; Windows and vendor installation remain unsupported. Keep this private one-hour address to yourself.",
    identity: "1. Confirm the destination",
    identityHint: "Use your deployed Platform API address and exact Lab / Gateway IDs. The service directory must be shared with the existing Gateway journal; do not create another one to bypass running work.",
    directory: "Service directory",
    station: "Workstation name",
    reviewIdentity: "Review local identity",
    pairing: "2. Pair with Platform",
    pairHint: "Create a short-lived code for the disabled Gateway in Platform. Paste it here, then compare the full fingerprint on both sides before approving in Platform. The code is never saved.",
    pairCode: "Pairing code",
    pair: "Claim this code",
    pairHistory: "Saved pairing receipt",
    refreshPairing: "Check Platform pairing status",
    prepare: "3. Prepare the exact installation",
    filesHint: "Choose a locally tested Adapter Package, an independently trusted Gateway SDK wheel, and the private JSON configuration. Selected files are copied only into this local service directory, not sent to Platform. Copies remain for review/recovery; this assistant does not automatically delete them.",
    package: "Adapter Package ZIP",
    sdk: "Trusted Gateway SDK wheel",
    config: "Private adapter configuration JSON",
    sdkDigest: "SDK SHA-256 from an independent trusted source",
    digestHint: "Do not trust a checksum supplied only by an unreviewed adapter or derive trust from the downloaded file itself.",
    previewInstall: "Preview installation inputs",
    handoff: "Download the PUBLIC request below. In Platform → Instrument Gateways → Install & qualify, select the equipment and approved package, compare the identity and authorize. Never upload gateway.json or a private installation request.",
    requests: "Saved installation request",
    download: "Download PUBLIC request",
    checkInstall: "Check approval / review installation",
    next: "An installed receipt is not permission to control equipment. Continue independent qualification and active-version review in Platform, then use the separately confirmed local activation launcher. No startup or unattended service is installed by this assistant.",
    reviewTitle: "Review the exact impact",
    confirm: "Confirm",
    cancel: "Cancel",
    working: "Working… Keep this window open. After uncertainty, check saved status before retrying.",
    reviewLocal: "I reviewed this exact destination and the local files that will be created. This does not approve hardware control.",
    reviewSource: "I independently reviewed the source and dependencies and authorize this exact inactive local installation. This does not authorize startup or equipment control.",
    error: "Operation not confirmed. ",
    setupFailed: "Check the exact destination, selected files, independent SDK checksum, private directory permissions and a fresh preview. If work was already confirmed, reload this page and check the saved status before trying again.",
    platformFailed: "Platform did not confirm the operation. Check the connection and the saved pairing or installation status before retrying. Do not create another identity or assume the operation failed.",
    fileFailed: "This local copy was not confirmed. Check the file size (config: 16 KiB; package / SDK: 64 MiB), directory permissions and retained-copy quota (64 files / 256 MiB). Preserve files referenced by saved installation requests.",
    session: "Open the private local address printed by the assistant. Restart it if the one-hour session has expired; saved work remains.",
    select: "Select a saved item",
    chooseFiles: "Select all three files and wait for their local copies to finish.",
    copied: "Private local copy saved",
    noApproval: "This authorization is not current. Review its status in Platform; do not install.",
  },
  zh: {
    language: "语言",
    title: "本地设备接入向导",
    intro: "配对本机、准备准确的安装请求、执行已审核安装并回传回执。此向导不启动适配器，也不控制设备。",
    boundary: "仅限本机使用。配对、源码审核、安装、真机验收和启动分别授权。目前仅支持 POSIX / 纯 Python 安装，不支持 Windows 或厂商软件安装。请勿分享包含一小时会话凭据的本地地址。",
    identity: "1. 核对接入位置",
    identityHint: "填写部署实例的 API 地址及准确的 Lab / Gateway ID。服务目录必须与已有 Gateway 的任务日志共用，不要另建目录绕过正在运行的工作。",
    directory: "服务目录",
    station: "工作站名称",
    reviewIdentity: "预览本地身份",
    pairing: "2. 与 Platform 配对",
    pairHint: "在 Platform 为已停用的网关创建短时配对码，粘贴到下方；比对两端的完整指纹后，再回到 Platform 批准。配对码不会保存。",
    pairCode: "配对码",
    pair: "提交配对码",
    pairHistory: "已保存的配对回执",
    refreshPairing: "查询 Platform 配对状态",
    prepare: "3. 准备准确的安装",
    filesHint: "选择已在本地测试的适配包、独立信任的 Gateway SDK wheel 和私有 JSON 配置。选择后仅复制到本机服务目录，不发送给 Platform。文件为审核和恢复保留，向导不会自动删除。",
    package: "Adapter Package ZIP",
    sdk: "可信 Gateway SDK wheel",
    config: "适配器私有 JSON 配置",
    sdkDigest: "来自独立可信来源的 SDK SHA-256",
    digestHint: "不要只相信未审核适配包提供的校验值，也不要把下载文件自身算出的校验值当成独立信任来源。",
    previewInstall: "预览安装输入",
    handoff: "下载下方的公开请求。在 Platform → 仪器网关 → 安装与验收中，选择准确设备和已审核适配包，比对身份后授权。不要上传 gateway.json 或私有安装请求。",
    requests: "已保存的安装请求",
    download: "下载公开请求",
    checkInstall: "查询批准并预览安装",
    next: "安装回执不表示可以控制设备。请继续在 Platform 独立验收、审核活动版本，再通过单独确认的本地启动器运行。本向导不会安装自启动或无人值守服务。",
    reviewTitle: "核对准确影响",
    confirm: "确认",
    cancel: "取消",
    working: "正在处理，请保持窗口打开。结果不确定时先查询已保存状态，再决定是否重试。",
    reviewLocal: "我已核对准确位置及将创建的本地文件。这不授予设备控制权限。",
    reviewSource: "我已独立审核源码和依赖，批准这一次准确的本地非活动安装。这不批准启动或设备控制。",
    error: "操作尚未确认。",
    setupFailed: "请核对准确位置、所选文件、独立 SDK 校验值、私有目录权限，并重新预览。如果已经确认过操作，请刷新页面并查询已保存状态，再决定是否重试。",
    platformFailed: "Platform 尚未确认操作。请检查连接并查询已保存的配对或安装状态后再重试；不要另建身份，也不要直接认定操作失败。",
    fileFailed: "尚未确认本地副本。请检查文件大小（配置 16 KiB，适配包 / SDK 64 MiB）、目录权限及保留副本配额（64 个文件 / 256 MiB）。不要删除已保存安装请求引用的文件。",
    session: "请打开向导终端显示的私有本地地址。会话超过一小时需重启向导，已保存的工作不会丢失。",
    select: "选择已保存条目",
    chooseFiles: "请选择三个文件，并等待本地副本保存完成。",
    copied: "已保存私有本地副本",
    noApproval: "此授权已不是有效状态，请在 Platform 核对，不能继续安装。",
  },
}

function translate() {
  document.documentElement.lang = language
  $("language").value = language
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = words[language][node.dataset.i18n]
  })
}

function setBusy(value) {
  busy = value
  document.querySelectorAll("button, input, select").forEach((node) => {
    node.disabled = value
  })
  $("confirm").disabled = value || !$("reviewed").checked
  $("activity").textContent = value ? words[language].working : ""
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
    $("error").textContent = words[language].error + error.message
    $("error").hidden = false
  }
  finally { setBusy(false) }
}

async function send(path, body, type) {
  if (!/^[\w-]{43}$/.test(token))
    throw new Error(words[language].session)
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": type, "X-Airalogy-Setup": token }, body, credentials: "omit", redirect: "error" })
  const result = await response.json()
  if (!response.ok)
    throw new Error(response.status === 401 ? words[language].session : words[language][result.code] || words[language].setupFailed)
  return result
}
const call = (operation, data = {}) => send("/api", JSON.stringify({ operation, data }), "application/json")
function show(id, value) {
  $(id).textContent = JSON.stringify(value, null, 2)
}

function options(id, items, value, label) {
  const previous = $(id).value
  $(id).replaceChildren(new Option(words[language].select, ""), ...items.map(item => new Option(label(item), value(item))))
  if (items.some(item => value(item) === previous))
    $(id).value = previous
  else if (items.length === 1)
    $(id).value = value(items[0])
}

async function refresh() {
  saved = await call("state")
  $("root").textContent = saved.root
  $("identity-form").hidden = !!saved.scope
  $("scope").hidden = !saved.scope
  $("pair-section").hidden = !saved.scope
  $("install-section").hidden = !saved.scope
  if (saved.scope)
    show("scope", saved.scope)
  options("requests", saved.requests, item => item.local_id, item => item.request.id)
  options("pairings", saved.pairings, item => item.id, item => item.id)
}

function review(result, operation, source = false) {
  currentReview = { result, operation, source }
  show("impact", result.impact)
  $("reviewed").checked = false
  $("review-label").textContent = words[language][source ? "reviewSource" : "reviewLocal"]
  $("confirm").disabled = true
  $("review").showModal()
}

$("language").addEventListener("change", () => {
  language = $("language").value
  translate()
})
$("identity-form").addEventListener("submit", (event) => {
  event.preventDefault()
  const data = Object.fromEntries(new FormData(event.currentTarget))
  guarded(async () => review(await call("identity-preview", data), "identity-confirm"))
})
$("pair-form").addEventListener("submit", (event) => {
  event.preventDefault()
  const code = $("pair-code").value
  $("pair-code").value = ""
  guarded(async () => {
    const result = await call("pair", { code })
    show("pair-result", result)
    await refresh()
    $("pairings").value = result.id
  })
})
$("pair-status").addEventListener("click", () => guarded(async () => {
  if (!$("pairings").value)
    throw new Error(words[language].select)
  show("pair-result", await call("pairing-status", { id: $("pairings").value }))
}))
document.querySelectorAll("[data-kind]").forEach(input => input.addEventListener("change", () => {
  const kind = input.dataset.kind
  delete uploads[kind]
  $(`${kind}-info`).textContent = ""
  const file = input.files[0]
  if (!file)
    return
  guarded(async () => {
    const result = await send(`/upload/${kind}`, file, "application/octet-stream")
    uploads[kind] = result.path
    $(`${kind}-info`).textContent = `${words[language].copied}: ${file.name} · ${result.bytes} bytes`
  })
}))
$("install-form").addEventListener("submit", (event) => {
  event.preventDefault()
  guarded(async () => {
    if (Object.keys(uploads).length !== 3)
      throw new Error(words[language].chooseFiles)
    review(await call("installation-preview", { ...uploads, trusted_sdk_digest: $("sdk-digest").value }), "installation-confirm")
  })
})
$("download").addEventListener("click", () => guarded(async () => {
  const selected = saved.requests.find(item => item.local_id === $("requests").value)
  if (!selected)
    throw new Error(words[language].select)
  const url = URL.createObjectURL(new Blob([JSON.stringify(selected.request, null, 2)], { type: "application/json" }))
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = `airalogy-public-installation-${selected.request.id}.json`
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}))
$("install-status").addEventListener("click", () => guarded(async () => {
  if (!$("requests").value)
    throw new Error(words[language].select)
  const result = await call("installation-status", { local_id: $("requests").value })
  show("install-result", result.impact)
  if (!["authorized", "installing", "installed"].includes(result.impact.state))
    throw new Error(words[language].noApproval)
  review(result, "installation-apply", true)
}))
$("reviewed").addEventListener("change", () => {
  $("confirm").disabled = busy || !$("reviewed").checked
})
$("cancel").addEventListener("click", () => {
  currentReview = null
  $("review").close()
})
$("confirm").addEventListener("click", () => guarded(async () => {
  if (!currentReview || !$("reviewed").checked)
    return
  const { result, operation, source } = currentReview
  currentReview = null
  $("review").close()
  const data = { confirmation: result.confirmation, ...(source ? { source_reviewed: true } : {}) }
  const outcome = await call(operation, data)
  if (operation !== "identity-confirm")
    show("install-result", outcome)
  await refresh()
  if (outcome.local_id)
    $("requests").value = outcome.local_id
}))
translate()
guarded(refresh)

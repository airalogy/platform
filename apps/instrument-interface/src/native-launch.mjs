import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { lstat, open, realpath } from "node:fs/promises"
import { dirname, join } from "node:path"
import { canonical, checkInteger, checkObject, checkText, digest } from "./contract.mjs"
import { Evidence, readPrivateSelection, syncDirectory } from "./evidence.mjs"
import { validateNativeBundle, validateNativePin } from "./native-contract.mjs"
import { nativeCall, nativeFailureCode, validateNativeBuild } from "./native-transport.mjs"

const effects = Object.freeze({ initialization_may_control_equipment: true, application_may_access_network: true, application_may_show_ui: true, gatekeeper_not_bypassed: true, activates: false, reuses_existing_instance: false, arguments: false, custom_environment: false, ui_actions_approved: false, automatic_retry: false, physical_safe_stop: false })

export function validateLaunchPreview(preview) {
  checkObject(preview, ["schema", "id", "build_file", "bundle", "reason", "expires_at", "engine", "effects"])
  if (preview.schema !== "airalogy.native-launch-preview.v1" || typeof preview.id !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(preview.id) || canonical(preview.effects) !== canonical(effects))
    throw new Error("Select a bounded explicit native launch, not a UI action grant")
  checkText(preview.build_file, 4096)
  checkText(preview.reason, 2000)
  validateNativeBundle(preview.bundle)
  checkObject(preview.engine, ["manifest", "os_version"])
  checkText(preview.engine.os_version)
  if (!Number.isFinite(Date.parse(preview.expires_at)) || new Date(preview.expires_at).toISOString() !== preview.expires_at)
    throw new Error("Launch approval needs a fixed expiry")
  if (Buffer.byteLength(canonical(preview)) > 131072)
    throw new Error("Launch preview exceeds its bound")
  return preview
}

export async function prepareNativeLaunch({ buildFile, bundlePath, reason, workspace, durationSeconds = 300 }) {
  checkText(reason, 2000)
  checkInteger(durationSeconds, 30, 900)
  const { manifest } = await validateNativeBuild(buildFile)
  const doctor = await nativeCall(buildFile, { operation: "doctor" })
  const bundle = await nativeCall(buildFile, { operation: "launch_probe", bundle_path: bundlePath })
  const preview = validateLaunchPreview({ schema: "airalogy.native-launch-preview.v1", id: randomUUID(), build_file: buildFile, bundle, reason, expires_at: new Date(Date.now() + durationSeconds * 1000).toISOString(), engine: { manifest, os_version: doctor.os_version }, effects })
  const evidence = await Evidence.create(workspace, preview)
  await evidence.write("request.json", Buffer.from(canonical({ preview, preview_digest: digest(preview) })))
  return { request_file: join(evidence.directory, "request.json"), preview_file: join(evidence.directory, "preview.json"), preview_digest: digest(preview), expires_at: preview.expires_at, applications_opened: false, model_called: false }
}

async function privateJSON(path) {
  const directory = dirname(path)
  if (await realpath(directory) !== directory)
    throw new Error("Select a canonical private launch workspace")
  for (const target of [directory, path]) {
    const info = await lstat(target)
    if (info.isSymbolicLink() || info.uid !== process.getuid() || (info.mode & 0o077) || (target === directory ? !info.isDirectory() : !info.isFile() || info.nlink !== 1))
      throw new Error("Launch approval and receipts must stay owner-only")
  }
  return JSON.parse(await readPrivateSelection(path))
}

async function readRequest(path) {
  if (join(dirname(path), "request.json") !== path)
    throw new Error("Select the exact prepared launch request")
  const request = await privateJSON(path)
  checkObject(request, ["preview", "preview_digest"])
  validateLaunchPreview(request.preview)
  if (request.preview_digest !== digest(request.preview) || canonical(await privateJSON(join(dirname(path), "preview.json"))) !== canonical(request.preview))
    throw new Error("The reviewed launch preview changed")
  return request
}

export async function runNativeLaunch(path, { confirmation, acknowledgeInitialization = false }) {
  const { preview, preview_digest: previewDigest } = await readRequest(path)
  if (acknowledgeInitialization !== true || confirmation !== previewDigest)
    throw new Error("Confirm the exact launch preview and acknowledge possible equipment initialization")
  if (Date.parse(preview.expires_at) <= Date.now())
    throw new Error("Launch approval expired; prepare a fresh review")
  const { manifest } = await validateNativeBuild(preview.build_file)
  const doctor = await nativeCall(preview.build_file, { operation: "doctor" })
  if (canonical(preview.engine) !== canonical({ manifest, os_version: doctor.os_version }))
    throw new Error("Launch runtime changed; prepare a fresh review")
  if (doctor.interactive_session?.ready !== true)
    throw new Error("interactive_session_required")
  const current = await nativeCall(preview.build_file, { operation: "launch_probe", bundle_path: preview.bundle.bundle_path })
  if (canonical(current) !== canonical(preview.bundle))
    throw new Error("Selected application changed after review")
  const root = dirname(path)
  // Exclusive, flushed before the helper receives the launch request. Never
  // remove this marker for recovery, even if LaunchServices returns no receipt.
  const marker = await open(join(root, "launch.started"), "wx", 0o600)
  try {
    await marker.writeFile(previewDigest)
    await marker.sync()
  }
  finally { await marker.close() }
  await syncDirectory(root)
  const evidence = new Evidence(root)
  await evidence.append("launch_intent", { preview_digest: previewDigest, hardware_qualified: false })
  let attempted = false
  try {
    if (Date.parse(preview.expires_at) <= Date.now())
      throw new Error("Launch approval expired before dispatch")
    attempted = true
    const result = await nativeCall(preview.build_file, { operation: "launch_application", bundle: preview.bundle }, { timeout: 30000 })
    checkObject(result, ["pin", "identity_verified", "hardware_qualified", "ui_actions_approved", "application_left_running"])
    validateNativePin(result.pin)
    if (canonical(result.pin.bundle) !== canonical(preview.bundle) || result.identity_verified !== true || result.hardware_qualified !== false || result.ui_actions_approved !== false || result.application_left_running !== true)
      throw new Error("Launched application identity could not be verified")
    const receipt = { preview_digest: previewDigest, result }
    await evidence.write("launch-result.json", Buffer.from(canonical(receipt)))
    await evidence.append("launch_identity_verified", { receipt_digest: digest(receipt), ui_actions_approved: false, hardware_qualified: false })
    return { ...result, receipt_file: join(root, "launch-result.json"), current_process_state: "identity_verified_at_launch" }
  }
  catch (error) {
    await evidence.write("launch-failed.json", Buffer.from(canonical({ preview_digest: previewDigest, reason: nativeFailureCode(error), launch_attempted: attempted, retry_allowed: false })))
    throw new Error(`Application launch stopped; retain private evidence and reconcile without relaunching: ${root}`)
  }
}

export async function nativeLaunchStatus(path) {
  const { preview_digest: previewDigest, preview } = await readRequest(path)
  const root = dirname(path)
  try {
    if ((await readPrivateSelection(join(root, "launch.started"))).toString("utf8") !== previewDigest)
      throw new Error("Launch marker changed")
  }
  catch (error) {
    if (error.code !== "ENOENT")
      throw error
    return { state: "not_started", current_process_state: "not_checked", applications_opened: false }
  }
  let receipt = null
  try {
    receipt = await privateJSON(join(root, "launch-result.json"))
  }
  catch (error) {
    if (error.code !== "ENOENT")
      throw error
  }
  if (receipt) {
    checkObject(receipt, ["preview_digest", "result"])
    checkObject(receipt.result, ["pin", "identity_verified", "hardware_qualified", "ui_actions_approved", "application_left_running"])
    validateNativePin(receipt.result.pin)
    if (receipt.preview_digest !== previewDigest || canonical(receipt.result.pin.bundle) !== canonical(preview.bundle) || receipt.result.identity_verified !== true || receipt.result.hardware_qualified !== false || receipt.result.ui_actions_approved !== false || receipt.result.application_left_running !== true)
      throw new Error("Saved launch receipt changed")
  }
  // Status is offline receipt inspection, including after upgrades/app exit.
  // It never runs even the old helper and never infers current physical state.
  return { state: receipt ? "reported_identity_verified" : "uncertain", result: receipt?.result ?? null, current_process_state: "not_checked", applications_opened: false, automatic_retry: false }
}

import { Buffer } from "node:buffer"
import { spawn } from "node:child_process"
import { constants } from "node:fs"
import { chmod, lstat, mkdir, open, realpath } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { bytesDigest, canonical, checkObject } from "./contract.mjs"
import { Evidence, readPrivateSelection, syncDirectory } from "./evidence.mjs"

const sources = ["Helper.swift", "Simulator.swift", "Info.plist"]
const sourceRoot = fileURLToPath(new URL("./macos/", import.meta.url))
const manifestSchema = "airalogy.native-macos-build.v2"
const allowedErrors = new Set(["invalid_request", "accessibility_permission_required", "target_changed", "selected_window_changed", "requires_one_window", "window_title_changed", "window_hidden_or_unmeasurable", "private_region_missing_or_ambiguous", "unexpected_dialog", "unsupported_target", "bound_exceeded", "accessibility_failure", "native_transport_failure", "owned_simulation_required", "stale_observation", "selected_window_not_focused", "selected_control_changed"])

export function nativeFailureCode(error) {
  return allowedErrors.has(error?.message) ? error.message : "native_validation_or_transport_failure"
}

function macOS() {
  if (process.platform !== "darwin" || !["arm64", "x64"].includes(process.arch))
    throw new Error("Native Accessibility requires a supported macOS host; no fallback execution")
}

// Fixed executables/arguments are selected by trusted local code, not a model.
// Do not inherit DYLD/NODE injection variables or arbitrary subprocess output.
async function command(executable, args, { input, timeout = 60000, maxBytes = 131072, native = false } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(executable, args, { env: { PATH: "/usr/bin:/bin:/usr/sbin:/sbin", TMPDIR: "/private/tmp" }, stdio: ["pipe", "pipe", "pipe"] })
    let output = Buffer.alloc(0)
    let errors = Buffer.alloc(0)
    let stopped = false
    const stop = () => {
      stopped = true
      child.kill("SIGKILL")
    }
    const timer = setTimeout(stop, timeout)
    child.stdout.on("data", (chunk) => {
      if (output.length + chunk.length > maxBytes)
        stop()
      else output = Buffer.concat([output, chunk])
    })
    child.stderr.on("data", (chunk) => {
      if (errors.length + chunk.length > maxBytes)
        stop()
      else errors = Buffer.concat([errors, chunk])
    })
    child.stdin.on("error", () => {})
    child.on("error", () => {
      clearTimeout(timer)
      reject(new Error("Native subprocess could not start"))
    })
    child.on("close", (code) => {
      clearTimeout(timer)
      if (stopped || code !== 0) {
        const reason = errors.toString("utf8").trim()
        reject(new Error(native && !stopped && allowedErrors.has(reason) ? reason : "Native subprocess refused, exceeded a bound or failed"))
      }
      else {
        resolve(output)
      }
    })
    child.stdin.end(input)
  })
}

export async function buildNative(root) {
  macOS()
  const sourceDigests = Object.fromEntries(await Promise.all(sources.map(async name => [name, bytesDigest(await readPrivateSelection(join(sourceRoot, name), 1048576))])))
  const evidence = await Evidence.create(root, { schema: manifestSchema, sources: sourceDigests, architecture: process.arch })
  const directory = evidence.directory
  const app = join(directory, "AiralogyNativeReader.app")
  const macos = join(app, "Contents", "MacOS")
  await mkdir(macos, { recursive: true, mode: 0o700 })
  const plist = await open(join(app, "Contents", "Info.plist"), "wx", 0o600)
  try {
    await plist.writeFile(await readPrivateSelection(join(sourceRoot, "Info.plist")))
    await plist.sync()
  }
  finally { await plist.close() }
  const helper = join(directory, "helper")
  const target = `${process.arch === "arm64" ? "arm64" : "x86_64"}-apple-macosx13.0`
  await command("/usr/bin/xcrun", ["swiftc", "-O", "-target", target, "-o", join(macos, "Simulator"), join(sourceRoot, "Simulator.swift")], { timeout: 120000 })
  await chmod(join(macos, "Simulator"), 0o700)
  // Ad-hoc integrity seal only. This is not vendor trust, notarization or qualification.
  await command("/usr/bin/codesign", ["--force", "--sign", "-", app])
  const simulatorHash = bytesDigest(await readPrivateSelection(join(macos, "Simulator"), 16777216))
  const simulatorInfoHash = bytesDigest(await readPrivateSelection(join(app, "Contents", "Info.plist")))
  const source = (await readPrivateSelection(join(sourceRoot, "Helper.swift"), 1048576)).toString("utf8")
  const sealed = source.replace("__AIRALOGY_OWNED_SIMULATOR_SHA256__", simulatorHash).replace("__AIRALOGY_OWNED_SIMULATOR_INFO_SHA256__", simulatorInfoHash)
  if (sealed === source || sealed.includes("__AIRALOGY_OWNED_SIMULATOR"))
    throw new Error("Native helper seal template changed")
  const sealedFile = await open(join(directory, "main.swift"), "wx", 0o600)
  try {
    await sealedFile.writeFile(sealed)
    await sealedFile.sync()
  }
  finally { await sealedFile.close() }
  await command("/usr/bin/xcrun", ["swiftc", "-O", "-target", target, "-o", helper, join(directory, "main.swift")], { timeout: 120000 })
  await chmod(helper, 0o700)
  const manifest = { schema: manifestSchema, architecture: process.arch, sources: sourceDigests, sealed_source_sha256: bytesDigest(Buffer.from(sealed)), helper_sha256: bytesDigest(await readPrivateSelection(helper, 16777216)), simulator_sha256: simulatorHash, simulator_info_sha256: simulatorInfoHash }
  // Refuse a source change during compilation instead of retaining false provenance.
  for (const name of sources) {
    if (bytesDigest(await readPrivateSelection(join(sourceRoot, name), 1048576)) !== sourceDigests[name])
      throw new Error("Native source changed during compilation; build a fresh workspace")
  }
  await evidence.write("native-build.json", Buffer.from(canonical(manifest)))
  await syncDirectory(directory)
  return { build_file: join(directory, "native-build.json"), simulator_app: app, helper, applications_opened: false, permissions_changed: false }
}

export async function validateNativeBuild(path) {
  macOS()
  const directory = dirname(path)
  if (join(directory, "native-build.json") !== path || await realpath(directory) !== directory)
    throw new Error("Select an exact native build manifest without symlink parents")
  for (const selected of [directory, path, join(directory, "helper")]) {
    const info = await lstat(selected)
    if (info.isSymbolicLink() || info.uid !== process.getuid() || (info.mode & 0o077) || (selected !== directory && (!info.isFile() || info.nlink !== 1)))
      throw new Error("Native builds must remain private and owned by this operator")
  }
  const manifest = JSON.parse(await readPrivateSelection(path))
  checkObject(manifest, ["schema", "architecture", "sources", "sealed_source_sha256", "helper_sha256", "simulator_sha256", "simulator_info_sha256"])
  checkObject(manifest.sources, sources)
  if (manifest.schema !== manifestSchema || manifest.architecture !== process.arch)
    throw new Error("Native build schema or architecture changed")
  for (const name of sources) {
    if (manifest.sources[name] !== bytesDigest(await readPrivateSelection(join(sourceRoot, name), 1048576)))
      throw new Error("Native source version changed; rebuild and review again")
  }
  const helper = join(directory, "helper")
  // A locally built helper is trusted executable code, never a model attachment.
  // The operator/host account is the trust boundary, not a forged same-UID manifest.
  if (manifest.helper_sha256 !== bytesDigest(await readPrivateSelection(helper, 16777216)))
    throw new Error("Native helper binary changed")
  if (manifest.sealed_source_sha256 !== bytesDigest(await readPrivateSelection(join(directory, "main.swift"), 1048576)))
    throw new Error("Native sealed build source changed")
  return { manifest, helper, directory }
}

export async function nativeCall(buildFile, request, { timeout = 15000 } = {}) {
  const { helper } = await validateNativeBuild(buildFile)
  const input = Buffer.from(canonical(request))
  if (input.length > 131072)
    throw new Error("Native request exceeds its bound")
  // Open the exact checked binary without following a final symlink and verify
  // immediately before launch; a malicious same-UID host remains out of scope.
  const handle = await open(helper, constants.O_RDONLY | constants.O_NOFOLLOW)
  try {
    const info = await handle.stat()
    if (!info.isFile() || info.nlink !== 1)
      throw new Error("Native helper changed")
    const output = await command(helper, [], { input, timeout, native: true })
    await validateNativeBuild(buildFile)
    return JSON.parse(output)
  }
  finally { await handle.close() }
}

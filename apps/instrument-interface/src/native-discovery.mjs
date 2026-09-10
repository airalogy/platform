import { Buffer } from "node:buffer"
import { spawn } from "node:child_process"
import { constants } from "node:fs"
import { lstat, open, opendir, realpath } from "node:fs/promises"
import { release } from "node:os"
import { basename, dirname, isAbsolute, join, normalize, relative } from "node:path"
import { fileURLToPath } from "node:url"
import { bytesDigest, canonical, checkInteger, checkObject, checkText, digest } from "./contract.mjs"
import { Evidence, readPrivateSelection } from "./evidence.mjs"

const limits = Object.freeze({ entries: 1000, applications: 40, seconds: 15, metadata_bytes: 1048576 })
const effects = Object.freeze({ applications_opened: false, executables_read: false, ui_observed: false, model_called: false, uploaded: false, signature_verified: false, hardware_qualified: false })
const worker = fileURLToPath(new URL("./native-discovery-worker.mjs", import.meta.url))
const sourceNames = ["native-discovery.mjs", "native-discovery-worker.mjs", "contract.mjs", "evidence.mjs"]

function macOS() {
  if (process.platform !== "darwin")
    throw new Error("Application discovery requires macOS; no alternative scanner is invoked")
}

async function engine() {
  macOS()
  return { node: process.version, architecture: process.arch, os_release: release(), sources: Object.fromEntries(await Promise.all(sourceNames.map(async name => [name, bytesDigest(await readPrivateSelection(fileURLToPath(new URL(name, import.meta.url)), 1048576))]))) }
}

async function directoryIdentity(path) {
  checkText(path, 4096)
  if (!isAbsolute(path) || path === "/" || path.split("/").some(part => part.toLowerCase().endsWith(".app")) || await realpath(path) !== path)
    throw new Error("Select one canonical application directory, not a disk root, link or bundle interior")
  const info = await lstat(path, { bigint: true })
  if (!info.isDirectory() || info.isSymbolicLink())
    throw new Error("Select a physical application directory")
  return { path, device: String(info.dev), inode: String(info.ino) }
}

function outside(directory, path) {
  if (!isAbsolute(path))
    return false
  const distance = relative(directory, path)
  return distance === ".." || distance.startsWith("../")
}

export function validateDiscoveryPreview(value) {
  checkObject(value, ["schema", "directory", "depth", "limits", "effects", "engine", "expires_at"])
  checkObject(value.directory, ["path", "device", "inode"])
  checkText(value.directory.path, 4096)
  if (value.schema !== "airalogy.native-discovery-preview.v1" || !isAbsolute(value.directory.path) || value.directory.path === "/" || ![value.directory.device, value.directory.inode].every(item => typeof item === "string" && /^\d{1,30}$/.test(item)) || canonical(value.limits) !== canonical(limits) || canonical(value.effects) !== canonical(effects))
    throw new Error("Invalid application discovery scope")
  checkInteger(value.depth, 0, 2)
  checkObject(value.engine, ["node", "architecture", "os_release", "sources"])
  checkObject(value.engine.sources, sourceNames)
  for (const key of ["node", "architecture", "os_release"])
    checkText(value.engine[key])
  if (!Object.values(value.engine.sources).every(item => typeof item === "string" && /^[a-f0-9]{64}$/.test(item)) || !Number.isFinite(Date.parse(value.expires_at)) || new Date(value.expires_at).toISOString() !== value.expires_at)
    throw new Error("Invalid discovery runtime or expiry")
  return value
}

export async function prepareNativeDiscovery({ directory, depth = 0, workspace }) {
  macOS()
  checkInteger(depth, 0, 2)
  const identity = await directoryIdentity(directory)
  if (!outside(directory, workspace))
    throw new Error("Keep discovery evidence outside the selected directory")
  const preview = validateDiscoveryPreview({ schema: "airalogy.native-discovery-preview.v1", directory: identity, depth, limits, effects, engine: await engine(), expires_at: new Date(Date.now() + 300000).toISOString() })
  // No directory enumeration, app metadata or process list is read in preparation.
  const evidence = await Evidence.create(workspace, preview)
  await evidence.write("request.json", Buffer.from(canonical({ preview, preview_digest: digest(preview) })))
  return { request_file: join(evidence.directory, "request.json"), preview_file: join(evidence.directory, "preview.json"), preview_digest: digest(preview), ...effects }
}

async function privateJSON(path) {
  if (await realpath(dirname(path)) !== dirname(path))
    throw new Error("Discovery evidence must use a canonical private directory")
  for (const target of [dirname(path), path]) {
    const info = await lstat(target)
    if (info.uid !== process.getuid() || (info.mode & 0o077) || info.isSymbolicLink() || (target === path ? !info.isFile() || info.nlink !== 1 : !info.isDirectory()))
      throw new Error("Discovery evidence must stay owner-only and unlinked")
  }
  return JSON.parse(await readPrivateSelection(path))
}

async function request(path) {
  if (join(dirname(path), "request.json") !== path)
    throw new Error("Select the exact prepared discovery request")
  const saved = await privateJSON(path)
  checkObject(saved, ["preview", "preview_digest"])
  validateDiscoveryPreview(saved.preview)
  if (digest(saved.preview) !== saved.preview_digest || canonical(await privateJSON(join(dirname(path), "preview.json"))) !== canonical(saved.preview))
    throw new Error("Discovery preview changed")
  return saved
}

// Fixed trusted parser/worker, never an executable from an application bundle.
// Pipe only selected bounded bytes, scrub injection variables, bound output/time.
async function subprocess(executable, args, input, timeout, maxBytes, group = false) {
  return new Promise((resolve, reject) => {
    const child = spawn(executable, args, { env: { PATH: "/usr/bin:/bin", TMPDIR: "/private/tmp" }, stdio: ["pipe", "pipe", "ignore"], detached: group })
    let output = Buffer.alloc(0)
    let stopped = false
    const stop = () => {
      stopped = true
      // The worker owns a separate group: timeout also stops its fixed parser,
      // never a discovered application or the operator's other processes.
      try {
        group ? process.kill(-child.pid, "SIGKILL") : child.kill("SIGKILL")
      }
      catch { /* The owned subprocess may already have exited. */ }
    }
    const timer = setTimeout(stop, timeout)
    child.stdout.on("data", (chunk) => {
      if (output.length + chunk.length > maxBytes)
        stop()
      else output = Buffer.concat([output, chunk])
    })
    child.stdin.on("error", () => {})
    child.on("error", () => {
      clearTimeout(timer)
      reject(new Error("Discovery subprocess unavailable"))
    })
    child.on("close", (code) => {
      clearTimeout(timer)
      if (stopped || code !== 0)
        reject(new Error("Discovery subprocess refused or exceeded its bound"))
      else resolve(output)
    })
    child.stdin.end(input)
  })
}

async function metadata(path, device) {
  const selected = join(path, "Contents", "Info.plist")
  if (await realpath(selected) !== selected)
    throw new Error("Linked metadata is excluded")
  const handle = await open(selected, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK)
  let bytes
  try {
    const before = await handle.stat({ bigint: true })
    if (!before.isFile() || String(before.dev) !== device || before.nlink !== 1n || before.size < 1n || before.size > BigInt(limits.metadata_bytes))
      throw new Error("Unbounded or nonregular metadata")
    bytes = Buffer.alloc(Number(before.size) + 1)
    const { bytesRead } = await handle.read(bytes, 0, bytes.length, 0)
    const after = await handle.stat({ bigint: true })
    if (BigInt(bytesRead) !== before.size || before.size !== after.size || before.mtimeNs !== after.mtimeNs || before.ctimeNs !== after.ctimeNs)
      throw new Error("Metadata changed during read")
    bytes = bytes.subarray(0, bytesRead)
  }
  finally { await handle.close() }
  const parsed = JSON.parse((await subprocess("/usr/bin/plutil", ["-convert", "json", "-o", "-", "--", "-"], bytes, 1500, 2097152)).toString("utf8"))
  if (!parsed || Array.isArray(parsed) || parsed.CFBundlePackageType !== "APPL")
    throw new Error("Not declared application metadata")
  const field = (key) => {
    if (parsed[key] === undefined)
      return null
    return checkText(parsed[key], 512)
  }
  return { name: field("CFBundleName"), display_name: field("CFBundleDisplayName"), bundle_id: field("CFBundleIdentifier"), version: field("CFBundleShortVersionString"), build_version: field("CFBundleVersion"), info_sha256: bytesDigest(bytes) }
}

export async function collectNativeApplications(preview) {
  macOS()
  validateDiscoveryPreview(preview)
  if (canonical(await directoryIdentity(preview.directory.path)) !== canonical(preview.directory))
    throw new Error("Discovery directory identity changed")
  const deadline = performance.now() + limits.seconds * 1000
  const queue = [{ path: preview.directory.path, depth: 0 }]
  const report = { schema: "airalogy.native-discovery-report.v1", preview_digest: digest(preview), directory: preview.directory, depth: preview.depth, applications: [], entries_examined: 0, skipped: { hidden: 0, links: 0, other_filesystems: 0, depth: 0, bundles: 0, unreadable: 0 }, stopped_reason: null, ...effects }
  while (queue.length) {
    if (performance.now() >= deadline) {
      report.stopped_reason = "time_limit"
      break
    }
    const current = queue.shift()
    const names = []
    let before
    try {
      const identity = await directoryIdentity(current.path)
      if (identity.device !== preview.directory.device) {
        report.skipped.other_filesystems++
        continue
      }
      before = await lstat(current.path, { bigint: true })
      const directory = await opendir(current.path)
      for await (const entry of directory) {
        if (report.entries_examined >= limits.entries) {
          report.stopped_reason = "entry_limit"
          break
        }
        report.entries_examined++
        if (entry.name.startsWith(".")) {
          report.skipped.hidden++
          continue
        }
        names.push(entry.name)
      }
    }
    catch {
      if (current.depth === 0)
        throw new Error("Selected discovery directory unavailable")
      report.skipped.unreadable++
      continue
    }
    for (const name of names.sort()) {
      if (performance.now() >= deadline) {
        report.stopped_reason = "time_limit"
        break
      }
      const path = join(current.path, name)
      let info
      try {
        checkText(path, 4096)
        info = await lstat(path, { bigint: true })
        if (info.isSymbolicLink() || await realpath(path) !== path) {
          report.skipped.links++
          continue
        }
        if (String(info.dev) !== preview.directory.device) {
          report.skipped.other_filesystems++
          continue
        }
      }
      catch {
        report.skipped.unreadable++
        continue
      }
      if (!info.isDirectory())
        continue
      if (name.toLowerCase().endsWith(".app")) {
        if (report.applications.length >= limits.applications) {
          report.stopped_reason = "application_limit"
          break
        }
        const candidate = { bundle_path: path, directory_name: name, metadata_status: "unavailable", declared: null }
        try {
          candidate.declared = await metadata(path, preview.directory.device)
          candidate.metadata_status = "read"
        }
        catch { /* A malformed/unreadable app stays a candidate, never a verified target. */ }
        report.applications.push(candidate)
        if (Buffer.byteLength(canonical(report)) > 110000) {
          report.applications.pop()
          report.stopped_reason = "report_limit"
          break
        }
      }
      else if (/\.(?:framework|bundle|plugin|appex|kext|xpc|pkg)$/i.test(name)) {
        report.skipped.bundles++
      }
      else if (current.depth < preview.depth) {
        queue.push({ path, depth: current.depth + 1 })
      }
      else { report.skipped.depth++ }
    }
    const after = await lstat(current.path, { bigint: true })
    if (before.dev !== after.dev || before.ino !== after.ino || before.mtimeNs !== after.mtimeNs || before.ctimeNs !== after.ctimeNs)
      throw new Error("Discovery directory changed during enumeration")
    if (report.stopped_reason)
      break
  }
  if (canonical(await directoryIdentity(preview.directory.path)) !== canonical(preview.directory))
    throw new Error("Discovery directory changed")
  return validateDiscoveryReport(report, preview)
}

export function validateDiscoveryReport(report, preview) {
  checkObject(report, ["schema", "preview_digest", "directory", "depth", "applications", "entries_examined", "skipped", "stopped_reason", ...Object.keys(effects)])
  checkObject(report.skipped, ["hidden", "links", "other_filesystems", "depth", "bundles", "unreadable"])
  if (report.schema !== "airalogy.native-discovery-report.v1" || report.preview_digest !== digest(preview) || canonical(report.directory) !== canonical(preview.directory) || report.depth !== preview.depth || Object.entries(effects).some(([key, value]) => report[key] !== value) || ![null, "entry_limit", "application_limit", "time_limit", "report_limit"].includes(report.stopped_reason))
    throw new Error("Discovery report scope or authority changed")
  checkInteger(report.entries_examined, 0, limits.entries)
  for (const count of Object.values(report.skipped))
    checkInteger(count, 0, limits.entries)
  if (!Array.isArray(report.applications) || report.applications.length > limits.applications)
    throw new Error("Discovery result exceeds its application bound")
  const paths = new Set()
  for (const candidate of report.applications) {
    checkObject(candidate, ["bundle_path", "directory_name", "metadata_status", "declared"])
    checkText(candidate.bundle_path, 4096)
    const within = relative(preview.directory.path, candidate.bundle_path).split("/")
    if (!isAbsolute(candidate.bundle_path) || normalize(candidate.bundle_path) !== candidate.bundle_path || within.length > preview.depth + 1 || within.some(part => !part || part.startsWith(".")) || !candidate.bundle_path.toLowerCase().endsWith(".app") || basename(candidate.bundle_path) !== candidate.directory_name || paths.has(candidate.bundle_path))
      throw new Error("Discovery candidate escaped the selected scope")
    paths.add(candidate.bundle_path)
    if (candidate.metadata_status === "read") {
      checkObject(candidate.declared, ["name", "display_name", "bundle_id", "version", "build_version", "info_sha256"])
      for (const [key, value] of Object.entries(candidate.declared)) {
        if (key === "info_sha256") {
          if (typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value))
            throw new Error("Invalid metadata digest")
        }
        else if (value !== null) {
          checkText(value, 512)
        }
      }
    }
    else if (candidate.metadata_status !== "unavailable" || candidate.declared !== null) {
      throw new Error("Unknown discovery metadata state")
    }
  }
  if (Buffer.byteLength(canonical(report)) > 131072)
    throw new Error("Discovery report exceeds its byte bound")
  return report
}

export async function runNativeDiscovery(path, confirmation) {
  const saved = await request(path)
  if (confirmation !== saved.preview_digest || Date.parse(saved.preview.expires_at) <= Date.now())
    throw new Error("Confirm the current unexpired discovery scope")
  if (canonical(await engine()) !== canonical(saved.preview.engine))
    throw new Error("Discovery runtime changed; prepare a fresh preview")
  // Never scan the output workspace, nor silently collect newly created evidence.
  if (!outside(saved.preview.directory.path, dirname(path)))
    throw new Error("Keep discovery evidence outside the selected directory")
  const evidence = new Evidence(dirname(path))
  await evidence.write("discovery.started", Buffer.from(saved.preview_digest))
  const report = validateDiscoveryReport(JSON.parse((await subprocess(process.execPath, [worker], Buffer.from(canonical(saved.preview)), 20000, 131072, true)).toString("utf8")), saved.preview)
  if (canonical(await engine()) !== canonical(saved.preview.engine))
    throw new Error("Discovery result or runtime changed")
  await evidence.write("discovery-result.json", Buffer.from(canonical(report)))
  return { report_file: join(evidence.directory, "discovery-result.json"), applications_found: report.applications.length, stopped_reason: report.stopped_reason, ...effects }
}

export async function nativeDiscoveryResult(path) {
  const saved = await request(path)
  const report = await privateJSON(join(dirname(path), "discovery-result.json"))
  validateDiscoveryReport(report, saved.preview)
  return { report, current_application_state: "not_checked", snapshot_only: true }
}

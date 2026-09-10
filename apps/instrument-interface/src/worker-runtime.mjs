import { Buffer } from "node:buffer"
import { createHash } from "node:crypto"
import { createReadStream } from "node:fs"
import { lstat, opendir, readFile, readlink, realpath } from "node:fs/promises"
import { createRequire } from "node:module"
import { basename, dirname, isAbsolute, join, relative, sep } from "node:path"
import { fileURLToPath } from "node:url"
import { bytesDigest, canonical, digest } from "./contract.mjs"
import { Evidence, readPrivateSelection } from "./evidence.mjs"
import { validateWorkflow } from "./workflow.mjs"

const packageRoot = fileURLToPath(new URL("../", import.meta.url))
const inside = (root, path) => path === root || path.startsWith(`${root}${sep}`)

export async function filePin(path) {
  const before = await lstat(path)
  if (!before.isFile() || (before.mode & 0o022) || before.size > 536870912)
    throw new Error("Runtime files must be regular, bounded and not group/world writable")
  const hash = createHash("sha256")
  for await (const chunk of createReadStream(path))
    hash.update(chunk)
  const after = await lstat(path)
  if (before.dev !== after.dev || before.ino !== after.ino || before.size !== after.size || before.mtimeMs !== after.mtimeMs || before.ctimeMs !== after.ctimeMs)
    throw new Error("Runtime changed while inventorying")
  return { path, size: after.size, sha256: hash.digest("hex") }
}

export async function treePin(root, excludeNodeModules = false) {
  root = await realpath(root)
  const files = {}
  const links = {}
  let count = 0
  let size = 0
  async function visit(path) {
    const info = await lstat(path)
    if (++count > 20000 || ((info.mode & 0o022) && !info.isSymbolicLink()))
      throw new Error("Runtime tree exceeds its bounds or permits untrusted writes")
    const name = relative(root, path).split(sep).join("/")
    if (info.isSymbolicLink()) {
      if (!inside(root, await realpath(path)))
        throw new Error("Runtime symlink escapes its selected tree")
      links[name] = await readlink(path)
    }
    else if (info.isDirectory()) {
      for await (const entry of await opendir(path)) {
        if (!(excludeNodeModules && entry.name === "node_modules"))
          await visit(join(path, entry.name))
      }
    }
    else {
      const pinned = await filePin(path)
      size += pinned.size
      if (size > 2147483648)
        throw new Error("Selected runtime tree exceeds 2 GiB")
      files[name] = { size: pinned.size, sha256: pinned.sha256 }
    }
  }
  await visit(root)
  return { root, exclude_node_modules: excludeNodeModules, files, links }
}

export async function modulePins() {
  const roots = new Map()
  const resolutions = []
  const unavailable = []
  async function dependency(parent, name) {
    const require = createRequire(join(parent, "package.json"))
    const resolved = dirname(require.resolve(`${name}/package.json`))
    let lookup = null
    const preceding = []
    for (const candidate of require.resolve.paths(`${name}/package.json`) ?? []) {
      const path = join(candidate, name)
      try {
        await lstat(path)
        if (await realpath(path) === resolved) {
          lookup = path
          break
        }
        throw new Error("An earlier package lookup exists but cannot be pinned")
      }
      catch (error) {
        if (error.code !== "ENOENT")
          throw error
        preceding.push(path)
      }
    }
    if (!lookup)
      throw new Error("Cannot independently pin package resolution")
    if (preceding.length)
      unavailable.push(preceding)
    resolutions.push({ path: lookup, target: resolved })
    if (roots.has(resolved))
      return
    roots.set(resolved, await treePin(resolved))
    const metadata = JSON.parse(await readFile(join(resolved, "package.json")))
    for (const child of Object.keys(metadata.dependencies ?? {}).sort())
      await dependency(resolved, child)
    for (const child of Object.keys(metadata.optionalDependencies ?? {}).sort()) {
      if (Object.hasOwn(metadata.dependencies ?? {}, child))
        continue
      const localRequire = createRequire(join(resolved, "package.json"))
      let present = true
      try {
        localRequire.resolve(`${child}/package.json`)
      }
      catch (error) {
        if (error.code !== "MODULE_NOT_FOUND")
          throw error
        present = false
      }
      if (present) {
        await dependency(resolved, child)
      }
      else {
        const paths = (localRequire.resolve.paths(`${child}/package.json`) ?? []).map(path => join(path, child))
        for (const path of paths) {
          try {
            await lstat(path)
            throw new Error("Optional dependency is present but cannot be pinned")
          }
          catch (error) {
            if (error.code !== "ENOENT")
              throw error
          }
        }
        unavailable.push(paths)
      }
    }
  }
  // The reviewed backend imports these roots. Inventory their complete declared
  // dependency closure, not a model-selected command or arbitrary workstation.
  for (const name of ["playwright", "ajv"])
    await dependency(packageRoot, name)
  return { trees: [...roots.values()], resolutions, unavailable }
}

export async function previewWorkerRuntime(workflowFile, evidenceRoot) {
  if (process.platform === "win32" || !isAbsolute(workflowFile) || !isAbsolute(evidenceRoot))
    throw new Error("The local interface worker requires explicit POSIX paths")
  const workflowBytes = await readPrivateSelection(workflowFile, 524288)
  const workflow = validateWorkflow(JSON.parse(workflowBytes))
  if (workflow.definition.schema !== "airalogy.browser-interface.v1")
    throw new Error("The first managed worker supports browser workflows only")
  const rootInfo = await lstat(evidenceRoot)
  if (!rootInfo.isDirectory() || rootInfo.isSymbolicLink() || rootInfo.uid !== process.getuid() || (rootInfo.mode & 0o077))
    throw new Error("Select an existing owner-only worker evidence directory")
  // Pin the same dedicated headless executable used by this exact Playwright
  // release. Do not switch to a personal/full browser or download a fallback.
  const require = createRequire(join(packageRoot, "package.json"))
  const runtimeRequire = createRequire(require.resolve("playwright/package.json"))
  const { registry } = runtimeRequire("playwright-core/lib/coreBundle").registry
  const browser = await realpath(registry.findExecutable("chromium-headless-shell").executablePath())
  let browserRoot = dirname(browser)
  for (let depth = 0; depth < 8 && !/^chromium_headless_shell-\d+$/.test(basename(browserRoot)); depth++)
    browserRoot = dirname(browserRoot)
  if (!/^chromium_headless_shell-\d+$/.test(basename(browserRoot)))
    throw new Error("Select the installed Playwright Chromium runtime, not a personal browser")
  const dependencies = await modulePins()
  const runtime = {
    schema: "airalogy.interface-worker-runtime.v1",
    node: await filePin(await realpath(process.execPath)),
    entry: await realpath(join(packageRoot, "src/worker.mjs")),
    browser,
    package: await filePin(join(packageRoot, "package.json")),
    trees: [await treePin(join(packageRoot, "src")), ...dependencies.trees, await treePin(browserRoot)],
    resolutions: dependencies.resolutions,
    unavailable: dependencies.unavailable,
    workflow: { path: await realpath(workflowFile), sha256: bytesDigest(workflowBytes), workflow_digest: workflow.sha256 },
    evidence_root: await realpath(evidenceRoot),
  }
  if (Buffer.byteLength(canonical(runtime)) > 2097152)
    throw new Error("Worker inventory exceeds its manifest bound")
  const value = { schema: "airalogy.interface-worker-prepare.v1", runtime, application_opened: false, hardware_qualified: false }
  return { ...value, sha256: digest(value) }
}

export async function prepareWorkerRuntime(workflowFile, { evidenceRoot, workspace, confirmation }) {
  const preview = await previewWorkerRuntime(workflowFile, evidenceRoot)
  if (preview.sha256 !== confirmation)
    throw new Error("Review and confirm the exact current worker runtime")
  const evidence = await Evidence.create(workspace, preview)
  const raw = Buffer.from(canonical(preview.runtime))
  await evidence.write("runtime.json", raw)
  const config = { schema: "airalogy.interface-worker-config.v1", runtime_file: join(evidence.directory, "runtime.json"), runtime_sha256: bytesDigest(raw) }
  await evidence.write("config.json", Buffer.from(canonical(config)))
  return { config_file: join(evidence.directory, "config.json"), runtime_file: config.runtime_file, runtime_sha256: config.runtime_sha256, workflow_digest: preview.runtime.workflow.workflow_digest, application_opened: false, hardware_qualified: false }
}

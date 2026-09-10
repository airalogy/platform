import { Buffer } from "node:buffer"
import { lstat, realpath } from "node:fs/promises"
import { dirname, isAbsolute, join } from "node:path"
import { fileURLToPath } from "node:url"
import { bytesDigest, canonical, digest } from "./contract.mjs"
import { Evidence, readPrivateSelection } from "./evidence.mjs"
import { validateNativeDefinition } from "./native-contract.mjs"
import { validateNativeBuild } from "./native-transport.mjs"
import { filePin, modulePins, treePin } from "./worker-runtime.mjs"

const packageRoot = fileURLToPath(new URL("../", import.meta.url))

export async function previewNativeReadRuntime(definitionFile, evidenceRoot) {
  if (process.platform !== "darwin" || !isAbsolute(definitionFile) || !isAbsolute(evidenceRoot))
    throw new Error("The native read worker requires macOS and explicit private paths")
  const raw = await readPrivateSelection(definitionFile, 131072)
  const definition = validateNativeDefinition(JSON.parse(raw))
  // Preparation inventories trusted local code only. It does not invoke the
  // helper, inspect running apps, read UI contents, launch or grant TCC access.
  const { directory } = await validateNativeBuild(definition.selection.build_file)
  const info = await lstat(evidenceRoot)
  if (!info.isDirectory() || info.isSymbolicLink() || info.uid !== process.getuid() || (info.mode & 0o077))
    throw new Error("Select an existing owner-only evidence directory")
  const dependencies = await modulePins()
  const runtime = {
    schema: "airalogy.native-read-worker-runtime.v1",
    node: await filePin(await realpath(process.execPath)),
    entry: await realpath(join(packageRoot, "src/native-read-worker.mjs")),
    native_build: definition.selection.build_file,
    package: await filePin(join(packageRoot, "package.json")),
    trees: [await treePin(join(packageRoot, "src")), ...dependencies.trees, await treePin(directory)],
    resolutions: dependencies.resolutions,
    unavailable: dependencies.unavailable,
    definition: { path: await realpath(definitionFile), sha256: bytesDigest(raw), definition_digest: digest(definition) },
    evidence_root: await realpath(evidenceRoot),
  }
  // Evidence cannot grow inside an integrity-pinned build tree.
  const evidenceRelative = runtime.evidence_root.slice(directory.length)
  if (runtime.evidence_root === directory || (runtime.evidence_root.startsWith(directory) && evidenceRelative.startsWith("/")))
    throw new Error("Keep worker evidence outside the selected native build")
  if (Buffer.byteLength(canonical(runtime)) > 2097152)
    throw new Error("Native worker inventory exceeds its bound")
  const value = { schema: "airalogy.native-read-worker-prepare.v1", runtime, application_opened: false, interface_read: false, actions_authorized: false, hardware_qualified: false }
  return { ...value, sha256: digest(value) }
}

export async function prepareNativeReadRuntime(definitionFile, { evidenceRoot, workspace, confirmation }) {
  const preview = await previewNativeReadRuntime(definitionFile, evidenceRoot)
  if (preview.sha256 !== confirmation)
    throw new Error("Review and confirm the exact current native read runtime")
  const build = dirname(preview.runtime.native_build)
  const selectedWorkspace = await realpath(workspace)
  if (selectedWorkspace === build || selectedWorkspace.startsWith(`${build}/`))
    throw new Error("Keep runtime descriptors outside the selected native build")
  const evidence = await Evidence.create(workspace, preview)
  const raw = Buffer.from(canonical(preview.runtime))
  await evidence.write("runtime.json", raw)
  const config = { schema: "airalogy.native-read-worker-config.v1", runtime_file: join(evidence.directory, "runtime.json"), runtime_sha256: bytesDigest(raw) }
  await evidence.write("config.json", Buffer.from(canonical(config)))
  return { config_file: join(evidence.directory, "config.json"), runtime_file: config.runtime_file, runtime_sha256: config.runtime_sha256, definition_digest: preview.runtime.definition.definition_digest, application_opened: false, interface_read: false, actions_authorized: false, hardware_qualified: false }
}

#!/usr/bin/env node
// Fixed macOS read worker. No application launch, click/fill, screenshots,
// model request or physical-stop claim. Runtime verification is in the SDK.
import { Buffer } from "node:buffer"
import { dirname, join } from "node:path"
import { bytesDigest, canonical, checkObject, digest } from "./contract.mjs"
import { Evidence, readPrivateSelection } from "./evidence.mjs"
import { validateNativeDefinition } from "./native-contract.mjs"
import { previewNativeRead, runNativeRead } from "./native-survey.mjs"
import { nativeCall, validateNativeBuild } from "./native-transport.mjs"

async function main() {
  if (process.platform !== "darwin" || process.argv.length !== 2)
    throw new Error("Select one fixed macOS read request on stdin")
  const chunks = []
  let size = 0
  for await (const part of process.stdin) {
    size += part.length
    if (size > 8192)
      throw new Error("Native read request exceeded its bound")
    chunks.push(part)
  }
  const request = JSON.parse(Buffer.concat(chunks))
  checkObject(request, ["schema", "operation", "job_id", "runtime_file", "runtime_sha256", "definition_digest"])
  if (request.schema !== "airalogy.native-read-worker-request.v1" || !["probe", "execute"].includes(request.operation) || (request.operation === "probe" ? request.job_id !== null : typeof request.job_id !== "string" || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(request.job_id)))
    throw new Error("Unsupported native read operation")
  const raw = await readPrivateSelection(request.runtime_file, 2097152)
  if (bytesDigest(raw) !== request.runtime_sha256)
    throw new Error("Native runtime descriptor changed")
  const runtime = JSON.parse(raw)
  if (runtime.schema !== "airalogy.native-read-worker-runtime.v1")
    throw new Error("Select a native read runtime")
  const source = await readPrivateSelection(runtime.definition.path, 131072)
  const definition = validateNativeDefinition(JSON.parse(source))
  if (bytesDigest(source) !== runtime.definition.sha256 || digest(definition) !== request.definition_digest || request.definition_digest !== runtime.definition.definition_digest || definition.selection.build_file !== runtime.native_build)
    throw new Error("The exact reviewed native read definition changed")
  const evidence = await Evidence.create(runtime.evidence_root, { schema: request.schema, operation: request.operation, job_id: request.job_id, runtime_sha256: request.runtime_sha256, definition_digest: request.definition_digest })
  await evidence.append("worker_intent", { operation: request.operation, job_id: request.job_id, definition_digest: request.definition_digest, actions_authorized: false, hardware_qualified: false })
  const preview = await previewNativeRead(definition)
  const { manifest } = await validateNativeBuild(runtime.native_build)
  const { pin } = definition.selection.target.source
  const ownedSimulator = pin.bundle.bundle_path === join(dirname(runtime.native_build), "AiralogyNativeReader.app") && pin.bundle.bundle_id === "org.airalogy.InstrumentInterfaceSimulator" && pin.bundle.executable_sha256 === manifest.simulator_sha256 && pin.bundle.info_sha256 === manifest.simulator_info_sha256
  let data
  if (request.operation === "probe") {
    // Metadata and existing permission diagnostics only, not a UI capture.
    const doctor = await nativeCall(runtime.native_build, { operation: "doctor" })
    data = { target: { identity_reference: `native-read:${digest(pin)}`, firmware: "not_applicable", application: pin.bundle.bundle_id, application_version: pin.bundle.version, driver_version: `native-read-worker-v1:${request.runtime_sha256.slice(0, 16)}`, os_version: preview.engine.os }, read_access: doctor.accessibility_trusted === true && doctor.interactive_session.ready === true, source_kind: "native_macos", owned_simulator: ownedSimulator, actions_executed: 0 }
  }
  else {
    const result = await runNativeRead(definition, { confirmation: preview.sha256, evidenceRoot: evidence.directory })
    if (result.actions_executed !== 0 || result.hardware_qualified !== false)
      throw new Error("Native worker must remain read-only")
    const values = JSON.parse(await readPrivateSelection(result.readback_file, 65536))
    data = { values, source_kind: "native_macos", owned_simulator: ownedSimulator, actions_executed: 0 }
  }
  const response = { schema: "airalogy.native-read-worker-response.v1", operation: request.operation, job_id: request.job_id, runtime_sha256: request.runtime_sha256, definition_digest: request.definition_digest, data, hardware_qualified: false }
  await evidence.append("worker_result", response)
  process.stdout.write(`${canonical(response)}\n`)
}
main().catch(() => {
  process.stderr.write("Selected native read failed; inspect private evidence without replay. No application action or physical stop is certified.\n")
  process.exitCode = 1
})

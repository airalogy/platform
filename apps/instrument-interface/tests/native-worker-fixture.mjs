// Test-only owned AppKit setup, excluded from the installed package. No target
// override, vendor software, model request or production authorization.
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { execFile, spawn } from "node:child_process"
import { once } from "node:events"
import { mkdtemp } from "node:fs/promises"
import { join } from "node:path"
import { fileURLToPath } from "node:url"
import { promisify } from "node:util"
import { canonical } from "../src/contract.mjs"
import { Evidence } from "../src/evidence.mjs"
import { validateNativeDefinition } from "../src/native-contract.mjs"
import { prepareNativeReadRuntime, previewNativeReadRuntime } from "../src/native-read-worker-runtime.mjs"
import { selectNative } from "../src/native-survey.mjs"
import { buildNative, nativeCall } from "../src/native-transport.mjs"
import { focusOwnedFixture } from "./native-fixture.mjs"

const repository = fileURLToPath(new URL("../../../", import.meta.url))

export function ownedReadDefinition(selection) {
  return validateNativeDefinition({
    schema: "airalogy.native-read-definition.v1",
    id: "owned.native.read",
    selection,
    identity: { locator: { kind: "ax_identifier", role: "AXStaticText", name: "app.identity" }, text: "Airalogy Native Reader 1.0 — simulation only" },
    controls: ["reader.status", "reader.result"].map(id => ({ id, locator: { kind: "ax_identifier", role: "AXStaticText", name: id }, read: "text", operations: ["read"] })),
  })
}

export async function prepareOwnedReadRuntime(built, pid, root) {
  const selection = await selectNative({ buildFile: built.build_file, bundlePath: built.simulator_app, pid, title: "Airalogy Native Reader — Simulation", redactIdentifiers: ["private.note"] })
  const evidence = await Evidence.create(root, { owned_fixture_only: true })
  const definition = ownedReadDefinition(selection)
  const file = join(evidence.directory, "definition.json")
  await evidence.write("definition.json", Buffer.from(canonical(definition)))
  const preview = await previewNativeReadRuntime(file, root)
  return prepareNativeReadRuntime(file, { evidenceRoot: root, workspace: root, confirmation: preview.sha256 })
}

export async function verifyIndependentNativeInstalls(configFile) {
  const sdkRoot = join(repository, "apps/instrument-gateway")
  const { stdout } = await promisify(execFile)("python3", [join(sdkRoot, "tests/native_read_acceptance.py"), configFile], { cwd: sdkRoot, env: { ...process.env, PYTHONPATH: join(sdkRoot, "src") }, timeout: 60000, maxBuffer: 65536 })
  const result = JSON.parse(stdout)
  assert.equal(result.independent_installs, 2)
  assert.equal(result.actual_native_reads, 2)
  assert.equal(result.hardware_qualified, false)
  return result
}

async function main() {
  const mode = process.argv[2]
  if (process.argv.length !== 3 || !["--installed", "--api"].includes(mode) || process.env.RUN_INSTRUMENT_NATIVE_JOB_TESTS !== "1")
    throw new Error("Choose --installed or --api with explicit owned-desktop acceptance")
  const root = await mkdtemp("/private/tmp/airalogy-native-read-acceptance-")
  const built = await buildNative(root)
  const doctor = await nativeCall(built.build_file, { operation: "doctor" })
  assert.equal(doctor.accessibility_trusted, true, "Existing operator-granted Accessibility required; tests never alter permissions")
  assert.equal(doctor.interactive_session.ready, true, "An active unlocked test session is required; tests never unlock it")
  const child = spawn(join(built.simulator_app, "Contents/MacOS/Simulator"), [], { stdio: ["ignore", "pipe", "ignore"] })
  const exited = once(child, "exit")
  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("Owned simulator startup did not complete")), 10000)
      child.stdout.once("data", () => {
        clearTimeout(timer)
        resolve()
      })
      child.once("error", (error) => {
        clearTimeout(timer)
        reject(error)
      })
    })
    await focusOwnedFixture(built.build_file, child.pid)
    const config = await prepareOwnedReadRuntime(built, child.pid, root)
    if (mode === "--installed") {
      process.stdout.write(`${canonical(await verifyIndependentNativeInstalls(config.config_file))}\n`)
    }
    else {
      await new Promise((resolve, reject) => {
        const runner = spawn("pnpm", ["research:integration", "-q", "--tb=short", "-k", "native_read_installed_job"], { cwd: repository, env: { ...process.env, INSTRUMENT_NATIVE_READ_CONFIG: config.config_file }, stdio: "inherit" })
        runner.once("error", reject)
        runner.once("exit", code => code === 0 ? resolve() : reject(new Error("Actual native/API acceptance failed")))
      })
    }
  }
  finally {
    if (child.exitCode === null && child.signalCode === null)
      child.kill("SIGTERM")
    await exited
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch(() => {
    process.stderr.write("Owned native acceptance failed; no vendor or hardware qualification.\n")
    process.exitCode = 1
  })
}

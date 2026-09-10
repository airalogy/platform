// Test setup only; excluded from the installed package. No vendor app path or
// arbitrary command is accepted, and production actions never acquire focus.
import assert from "node:assert/strict"
import { execFile } from "node:child_process"
import { join, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { parseArgs, promisify } from "node:util"
import { nativeCall, validateNativeBuild } from "../src/native-transport.mjs"

export async function focusOwnedFixture(buildFile, pid) {
  const { directory, manifest } = await validateNativeBuild(buildFile)
  const bundlePath = join(directory, "AiralogyNativeReader.app")
  const pin = await nativeCall(buildFile, { operation: "pin_process", bundle_path: bundlePath, pid })
  assert.equal(pin.bundle.bundle_id, "org.airalogy.InstrumentInterfaceSimulator")
  assert.equal(pin.bundle.executable_sha256, manifest.simulator_sha256)
  assert.equal(pin.bundle.info_sha256, manifest.simulator_info_sha256)
  assert.equal((await nativeCall(buildFile, { operation: "doctor" })).interactive_session.ready, true, "Tests never unlock or wake a graphical session")
  // Exactly one test-owned, already running application. This is test setup,
  // not a retry after an action refusal or an authority available to Aira.
  await promisify(execFile)("/usr/bin/open", ["-a", bundlePath], { timeout: 5000 })
  for (let index = 0; index < 30; index++) {
    const state = await nativeCall(buildFile, { operation: "inspect_windows", pin })
    if (state.frontmost === true && state.windows.length === 1 && state.windows[0].role === "AXWindow" && state.windows[0].title === "Airalogy Native Reader — Simulation" && state.windows[0].focused && state.windows[0].has_geometry && state.windows[0].minimized === false)
      return { owned_simulator_foreground: true, hardware_qualified: false }
    if (index === 29)
      assert.fail(`Owned fixture focus is not ready: ${JSON.stringify(state)}`)
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  throw new Error("Keep the explicitly selected owned test window in the foreground during GUI acceptance")
}

async function main() {
  const { values } = parseArgs({ options: { build: { type: "string" }, pid: { type: "string" } } })
  assert.match(values.pid ?? "", /^\d+$/)
  process.stdout.write(`${JSON.stringify(await focusOwnedFixture(values.build, Number(values.pid)))}\n`)
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(() => {
    process.stderr.write("Owned native fixture setup refused; check the active session and exact test build/process. No vendor action or hardware qualification.\n")
    process.exitCode = 1
  })
}

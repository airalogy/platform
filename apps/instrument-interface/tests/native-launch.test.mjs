/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { chmod, link, mkdtemp, realpath, symlink, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"
import { canonical, digest } from "../src/contract.mjs"
import { Evidence } from "../src/evidence.mjs"
import { nativeLaunchStatus, runNativeLaunch, validateLaunchPreview } from "../src/native-launch.mjs"

function preview() {
  return {
    schema: "airalogy.native-launch-preview.v1",
    id: "11111111-1111-4111-8111-111111111111",
    build_file: "/nonexistent/synthetic/native-build.json",
    bundle: { bundle_path: "/nonexistent/Synthetic.app", executable_path: "/nonexistent/Synthetic.app/Contents/MacOS/Synthetic", bundle_id: "org.airalogy.synthetic", version: "1.0", executable_sha256: "a".repeat(64), info_sha256: "b".repeat(64), code_directory_hash: "c".repeat(40) },
    reason: "Synthetic receipt validation, never launch this fixture",
    expires_at: new Date(Date.now() + 60000).toISOString(),
    engine: { manifest: { synthetic: true }, os_version: "Synthetic historical runtime" },
    effects: { initialization_may_control_equipment: true, application_may_access_network: true, application_may_show_ui: true, gatekeeper_not_bypassed: true, activates: false, reuses_existing_instance: false, arguments: false, custom_environment: false, ui_actions_approved: false, automatic_retry: false, physical_safe_stop: false },
  }
}

async function prepared(selected = preview()) {
  const root = await realpath(await mkdtemp(join(tmpdir(), "airalogy-launch-contract-")))
  const evidence = await Evidence.create(root, selected)
  await evidence.write("request.json", Buffer.from(canonical({ preview: selected, preview_digest: digest(selected) })))
  return { selected, evidence, path: join(evidence.directory, "request.json") }
}

test("launch previews cannot contain arbitrary commands or suppress startup effects", () => {
  const selected = preview()
  validateLaunchPreview(selected)
  for (const change of [
    item => item.schema = "airalogy.native-read-definition.v1",
    item => item.arguments = ["--unreviewed"],
    item => item.effects.activates = true,
    item => item.effects.gatekeeper_not_bypassed = false,
    item => item.effects.initialization_may_control_equipment = false,
    item => item.effects.physical_safe_stop = true,
    item => item.bundle.info_sha256 = "changed",
    item => item.bundle.info_sha256 = ["a".repeat(64)],
    item => item.bundle.code_directory_hash = ["c".repeat(40)],
    item => item.id = [item.id],
    item => item.expires_at = "2099-01-01",
    item => item.reason = " ",
    item => item.engine.command = "arbitrary executable",
  ]) {
    const invalid = structuredClone(selected)
    change(invalid)
    assert.throws(() => validateLaunchPreview(invalid))
  }
})

const posix = (name, fn) => test(name, { skip: process.platform === "win32" }, fn)
posix("missing confirmation or expired consent cannot even consult the nonexistent helper", async () => {
  const value = await prepared()
  await assert.rejects(runNativeLaunch(value.path, { confirmation: digest(value.selected) }), /acknowledge/)
  await assert.rejects(runNativeLaunch(value.path, { confirmation: "f".repeat(64), acknowledgeInitialization: true }), /Confirm/)
  assert.equal((await nativeLaunchStatus(value.path)).state, "not_started")
  const expired = await prepared({ ...preview(), expires_at: new Date(Date.now() - 1000).toISOString() })
  await assert.rejects(runNativeLaunch(expired.path, { confirmation: digest(expired.selected), acknowledgeInitialization: true }), /expired/)
})

posix("offline receipts distinguish no dispatch, uncertainty and historical identity without executing code", async () => {
  const value = await prepared()
  assert.deepEqual(await nativeLaunchStatus(value.path), { state: "not_started", current_process_state: "not_checked", applications_opened: false })
  await value.evidence.write("launch.started", Buffer.from(digest(value.selected)))
  const uncertain = await nativeLaunchStatus(value.path)
  assert.equal(uncertain.state, "uncertain")
  assert.equal(uncertain.automatic_retry, false)
  const result = { pin: { bundle: value.selected.bundle, process: { pid: 123, uid: 501, started_seconds: "123", started_microseconds: "123" } }, identity_verified: true, hardware_qualified: false, ui_actions_approved: false, application_left_running: true }
  await value.evidence.write("launch-result.json", Buffer.from(canonical({ preview_digest: digest(value.selected), result })))
  const reported = await nativeLaunchStatus(value.path)
  assert.deepEqual(reported.result, result)
  assert.equal(reported.state, "reported_identity_verified")
  assert.equal(reported.current_process_state, "not_checked")
  assert.equal(reported.applications_opened, false)
  await writeFile(join(value.evidence.directory, "launch-result.json"), canonical({ preview_digest: digest(value.selected), result: { ...result, ui_actions_approved: true } }))
  await assert.rejects(nativeLaunchStatus(value.path), /receipt changed/)
})

posix("private launch files reject links, public permissions and mismatched previews", async () => {
  const value = await prepared()
  await chmod(value.path, 0o644)
  await assert.rejects(nativeLaunchStatus(value.path), /owner-only/)
  await chmod(value.path, 0o600)
  const publicRoot = await realpath(await mkdtemp(join(tmpdir(), "airalogy-launch-public-")))
  await chmod(publicRoot, 0o755)
  // Only this test-owned directory is made public; never change system temp permissions.
  await assert.rejects(Evidence.create(publicRoot, value.selected), /owner-only/)
  const root = await realpath(await mkdtemp(join(tmpdir(), "airalogy-launch-links-")))
  for (const createLink of [symlink, link]) {
    const directory = await Evidence.create(root, value.selected)
    await createLink(value.path, join(directory.directory, "request.json"))
    await assert.rejects(nativeLaunchStatus(join(directory.directory, "request.json")), /owner-only/)
  }
  const changed = await prepared()
  await writeFile(changed.path, canonical({ preview: { ...changed.selected, reason: "Changed" }, preview_digest: digest(changed.selected) }))
  await assert.rejects(nativeLaunchStatus(changed.path), /preview changed/)
})

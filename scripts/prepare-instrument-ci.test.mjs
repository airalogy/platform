/* eslint-disable test/no-import-node-test -- CI preparation uses the standalone Node test runner. */
import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { chmodSync, mkdtempSync, realpathSync, rmSync, statSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { test } from "node:test"
import { browserProfile, hardenExecutable } from "./prepare-instrument-ci.mjs"

test("CI preparation refuses local and self-hosted environments before changing anything", () => {
  for (const environment of ["", "self-hosted"]) {
    const result = spawnSync(process.execPath, ["scripts/prepare-instrument-ci.mjs", "--executables"], {
      env: { ...process.env, GITHUB_ACTIONS: "true", RUNNER_ENVIRONMENT: environment },
      encoding: "utf8",
    })
    assert.notEqual(result.status, 0)
    assert.match(result.stderr, /restricted to disposable GitHub-hosted runners/)
  }
})

test("executable preparation removes only group/world write bits and rejects non-executables", () => {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "airalogy-ci-mode-")))
  try {
    const executable = join(root, "synthetic-executable")
    writeFileSync(executable, "synthetic test bytes; never executed")
    chmodSync(executable, 0o777)
    assert.equal(hardenExecutable(executable), executable)
    assert.equal(statSync(executable).mode & 0o777, 0o755)
    hardenExecutable(executable)
    assert.equal(statSync(executable).mode & 0o777, 0o755)
    chmodSync(executable, 0o600)
    assert.throws(() => hardenExecutable(executable), /independently installed executable/)
  }
  finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test("browser exception uses exact paths and rejects AppArmor pattern injection", () => {
  const profile = browserProfile(["/runner/chromium-123/chrome", "/runner/chromium_headless_shell-123/headless_shell"])
  assert.match(profile, /"\/runner\/chromium-123\/chrome"/)
  assert.equal(profile.match(/userns,/g).length, 2)
  for (const path of ["relative/chrome", "/runner/**/chrome", "/runner/@{HOME}/chrome", "/runner/[ab]/chrome", "/runner/\"chrome", "/runner/chrome\n}"])
    assert.throws(() => browserProfile([path]), /exact absolute executable paths/)
  assert.throws(() => browserProfile([]))
})

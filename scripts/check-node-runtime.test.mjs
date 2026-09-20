/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { copyFileSync, mkdirSync, mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"
import { assertNodeConfiguration, assertNodeRuntime, checkNodeConfiguration, checkNodeRuntime } from "./check-node-runtime.mjs"

test("local checks accept the supported Node line and reject incompatible versions early", () => {
  for (const version of ["22.12.0", "22.23.2"])
    assert.doesNotThrow(() => assertNodeRuntime(version, "22"))
  for (const version of ["20.20.2", "22.11.0", "24.0.0", "invalid"])
    assert.throws(() => assertNodeRuntime(version, "22"), /unsupported/)
})

test("CI pins cannot drift back to Node 20 or override the shared version file", () => {
  const configuration = {
    major: "22",
    engines: ">=22.12.0 <23",
    workflows: { "fixture.yml": "jobs:\n  lint:\n    steps:\n      - uses: actions/setup-node@v6\n        with:\n          node-version-file: .node-version\n" },
    dockerfile: "FROM node:22-bookworm-slim AS builder\n",
  }
  assert.doesNotThrow(() => assertNodeConfiguration(configuration))
  for (const setting of ["node-version: '20'", "node-version-file: .node-version\n          node-version: '20'", "node-version-file: another-file"]) {
    assert.throws(() => assertNodeConfiguration({ ...configuration, workflows: { bad: configuration.workflows["fixture.yml"].replace("node-version-file: .node-version", setting) } }), /must read/)
  }
  assert.throws(() => assertNodeConfiguration({ ...configuration, engines: ">=20" }), /aligned/)
  assert.throws(() => assertNodeConfiguration({ ...configuration, dockerfile: "FROM node:20-bookworm-slim AS builder" }), /production/)
  assert.throws(() => assertNodeConfiguration({ ...configuration, workflows: { bad: `on:\n  push:\n    paths: [apps/web/**]\n${configuration.workflows["fixture.yml"]}` } }), /must include/)
})

test("checked-in CI, runtime declarations and Docker use the same supported line", () => {
  checkNodeRuntime()
  checkNodeConfiguration()
})

test("Python-only CI gates start without a frontend node_modules installation", (t) => {
  const directory = mkdtempSync(join(tmpdir(), "platform-node-guard-"))
  t.after(() => rmSync(directory, { recursive: true, force: true }))
  mkdirSync(join(directory, "scripts"))
  for (const file of [".node-version", "package.json", "scripts/pre-push.mjs", "scripts/check-node-runtime.mjs"])
    copyFileSync(new URL(`../${file}`, import.meta.url), join(directory, file))
  const result = spawnSync(process.execPath, ["scripts/pre-push.mjs", "--check", "unknown-check"], { cwd: directory, encoding: "utf8" })
  assert.equal(result.status, 1)
  assert.match(result.stderr, /Specify one registered check ID/, "must reach check dispatch without loading YAML")
  assert.doesNotMatch(result.stderr, /MODULE_NOT_FOUND|Cannot find package/)
})

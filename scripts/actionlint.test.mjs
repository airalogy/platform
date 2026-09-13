/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
import { mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"
import { pins, requireActionlint, targetFor, verifyDigest, version } from "./actionlint.mjs"

test("workflow checker pins both archive and executable for each supported host", () => {
  assert.equal(version, "1.7.12")
  for (const platform of ["linux", "darwin"]) {
    for (const arch of ["x64", "arm64"]) {
      for (const digest of pins[targetFor(platform, arch)])
        assert.match(digest, /^[a-f0-9]{64}$/)
    }
  }
  assert.throws(() => targetFor("win32", "x64"), /Unsupported/)
  const original = Buffer.from("synthetic reviewed bytes")
  const digest = createHash("sha256").update(original).digest("hex")
  assert.equal(verifyDigest(original, digest), original)
  assert.throws(() => verifyDigest(Buffer.from("changed"), digest), /checksum mismatch/)
})

test("missing or changed cached tools fail closed without downloading or executing", () => {
  const directory = mkdtempSync(join(tmpdir(), "platform-actionlint-fixture-"))
  try {
    const binary = join(directory, "actionlint")
    assert.throws(() => requireActionlint(binary), /ci:tools:install/)
    writeFileSync(binary, "not a verified executable", { mode: 0o755 })
    assert.throws(() => requireActionlint(binary), /checksum mismatch/)
  }
  finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test("the actual pinned actionlint accepts valid workflows and rejects malformed expressions", () => {
  const executable = requireActionlint()
  const valid = "name: Fixture\non: push\njobs:\n  check:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo fixture\n"
  // GitHub expressions are deliberately literal, not JavaScript interpolation.
  // eslint-disable-next-line no-template-curly-in-string
  const invalidExpression = "echo ${{ nonexistent.value }}"
  for (const [input, status] of [[valid, 0], [valid.replace("echo fixture", invalidExpression), 1], [valid.replace("runs-on:", "runs-onn:"), 1]]) {
    const result = spawnSync(executable, ["-shellcheck=", "-pyflakes=", "-"], { input, encoding: "utf8", timeout: 10000 })
    assert.equal(result.error, undefined)
    assert.equal(result.status, status, result.stdout + result.stderr)
  }
})

/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { prepareObjectStorage, storageFingerprint, storageInputLabel, storageTestImage } from "./prepare-object-storage.mjs"

const image = (fingerprint = storageFingerprint(), architecture = "amd64") => ({ status: 0, stdout: JSON.stringify([{ Architecture: architecture, Config: { Labels: { [storageInputLabel]: fingerprint } } }]) })

test("storage image is reused only with matching source fingerprint and native architecture", () => {
  assert.equal(prepareObjectStorage({ run: () => image(), architecture: "x64" }), storageTestImage)
  for (const result of [image("old"), image(undefined, "arm64"), { status: 1 }])
    assert.throws(() => prepareObjectStorage({ run: () => result, architecture: "x64", verifyOnly: true }), /does not match/)
})

test("storage build verifies its output and never falls back after failures", () => {
  const calls = []
  prepareObjectStorage({ architecture: "x64", run: (cmd, args) => {
    calls.push([cmd, args])
    return calls.length === 1 ? { status: 1 } : calls.length === 2 ? { status: 0 } : image()
  } })
  assert.equal(calls.length, 3)
  assert.deepEqual(calls[1][1].slice(0, 5), ["build", "--label", `${storageInputLabel}=${storageFingerprint()}`, "--tag", storageTestImage])
  assert.throws(() => prepareObjectStorage({ run: () => ({ status: 1 }), architecture: "x64" }), /build failed/)
  assert.throws(() => prepareObjectStorage({ run: () => ({ error: new Error("timeout") }), architecture: "x64" }), /timeout/)
})

test("storage runtime labels match the locked upstream commits and include corresponding source", () => {
  const dockerfile = readFileSync("deploy/object-storage/Dockerfile", "utf8")
  const lock = readFileSync("deploy/object-storage/sources.env", "utf8")
  for (const name of ["MINIO", "MC"]) {
    const commit = new RegExp(`^${name}_COMMIT=([a-f0-9]{40})$`, "m").exec(lock)?.[1]
    assert.ok(commit)
    assert.ok(dockerfile.includes(`io.airalogy.${name.toLowerCase()}.commit="${commit}"`))
    assert.match(lock, new RegExp(`^${name}_SOURCE_SHA256=[a-f0-9]{64}$`, "m"))
  }
  assert.match(dockerfile, /COPY --from=source \/sources \/usr\/share\/airalogy-object-storage\/source/)
})

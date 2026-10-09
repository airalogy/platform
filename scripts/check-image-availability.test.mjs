/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"
import test from "node:test"
import { checkImageAvailability, checkStorageSourceAvailability, externalBuildInputs, imageReferences } from "./check-image-availability.mjs"

test("cold checks include pinned source-build bases and exact reachable source archives", async () => {
  const refs = externalBuildInputs()
  assert.ok(refs.some(ref => ref.startsWith("golang:") && ref.includes("@sha256:")))
  assert.ok(refs.some(ref => ref.startsWith("alpine:") && ref.includes("@sha256:")))
  assert.ok(!refs.some(ref => ref.startsWith("airalogy-platform-object-storage:")))
  const urls = []
  await checkStorageSourceAvailability(async (url, options) => {
    urls.push(url)
    assert.equal(options.method, "HEAD")
    assert.match(url, /^https:\/\/codeload.github.com\/minio\/(minio|mc)\/tar.gz\/[a-f0-9]{40}$/)
    return { ok: true }
  })
  assert.equal(urls.length, 2)
  await assert.rejects(checkStorageSourceAvailability(async () => ({ ok: false, status: 404 })), /source unavailable/)
})

test("image preflight reads static defaults without evaluating environment or shell input", () => {
  // eslint-disable-next-line no-template-curly-in-string -- Literal Compose interpolation is the input under test.
  assert.deepEqual(imageReferences("services:\n  storage:\n    image: ${MINIO_IMAGE:-quay.io/minio/minio:version}\n  redis:\n    image: redis:7-alpine\n"), ["quay.io/minio/minio:version", "redis:7-alpine"])
  // eslint-disable-next-line no-template-curly-in-string -- Unknown Compose variables must be rejected.
  for (const source of ["image: ${PRIVATE_IMAGE}", "image: $(echo-password)", "image: --help"])
    assert.throws(() => imageReferences(source))
  assert.equal(imageReferences(readFileSync("tests/e2e/compose.yml", "utf8")).length, 3)
})

test("anonymous manifest checks ignore local image caches and remove their private config", () => {
  const calls = []
  checkImageAvailability(["registry.example/image:v1", "registry.example/image:v1"], (...args) => {
    calls.push(args)
    assert.equal(args[0], "docker")
    assert.deepEqual(args[1].slice(2), ["buildx", "imagetools", "inspect", "--raw", "registry.example/image:v1"])
    assert.equal(args[2].env.DOCKER_CONFIG, args[1][1])
    assert.equal(args[2].env.DOCKER_AUTH_CONFIG, "")
    assert.ok(!existsSync(`${args[1][1]}/config.json`))
    assert.equal(args[2].timeout, 30_000)
    assert.equal(args[2].killSignal, "SIGKILL")
    return { status: 0, stdout: JSON.stringify({ schemaVersion: 2, manifests: [{}] }) }
  })
  assert.equal(calls.length, 1)
  assert.ok(!existsSync(calls[0][1][1]))
})

test("unavailable, malformed or timed-out image checks fail before later work", () => {
  assert.throws(() => checkImageAvailability([]), /empty/)
  for (const result of [{ status: 1, stderr: "unauthorized" }, { status: null, error: new Error("timeout") }, { status: 0, stdout: "{}" }]) {
    let count = 0
    let config
    assert.throws(() => checkImageAvailability(["registry.example/a:v1", "registry.example/b:v1"], (_, args) => {
      count++
      config = args[1]
      return result
    }))
    assert.equal(count, 1)
    assert.ok(!existsSync(config))
  }
})

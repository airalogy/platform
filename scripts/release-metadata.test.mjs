import assert from "node:assert/strict"
import { mkdtemp, readFile, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { createReleaseMetadata } from "./release-metadata-lib.mjs"

const repositoryRoot = path.resolve(import.meta.dirname, "..")

test("release metadata binds every deployable component by digest", async () => {
  const temporaryDirectory = await mkdtemp(path.join(os.tmpdir(), "platform-release-"))
  const metadataDirectory = path.join(temporaryDirectory, "metadata")
  const outputDirectory = path.join(temporaryDirectory, "output")
  const { mkdir } = await import("node:fs/promises")
  await mkdir(metadataDirectory)

  const components = ["api", "web", "protocol-executor", "postgres"]
  for (const [index, component] of components.entries()) {
    await writeFile(
      path.join(metadataDirectory, `${component}.repository`),
      `ghcr.io/airalogy/platform-${component}\n`,
    )
    await writeFile(
      path.join(metadataDirectory, `${component}.digest`),
      `sha256:${String(index + 1).repeat(64)}\n`,
    )
  }

  const { manifest, manifestDigest } = await createReleaseMetadata({
    repositoryRoot,
    metadataDirectory,
    outputDirectory,
    envTemplatePath: path.join(repositoryRoot, "deploy", "single-lab", ".env.example"),
    releaseTag: "v0.1.0",
    gitCommit: "a".repeat(40),
    createdAt: "2026-08-14T00:00:00Z",
  })

  assert.equal(manifest.product_version, "0.1.0")
  assert.equal(manifest.database.revision, "0008_record_exports")
  assert.match(manifest.components.protocol_executor.deployment_reference, /@sha256:/)
  assert.match(manifestDigest, /^[0-9a-f]{64}$/)

  const renderedEnvironment = await readFile(path.join(outputDirectory, ".env.example"), "utf8")
  assert.match(renderedEnvironment, /^AIRALOGY_RELEASE_METADATA_REQUIRED=true$/mu)
  assert.match(renderedEnvironment, /^AIRALOGY_API_IMAGE=.+@sha256:/mu)
})

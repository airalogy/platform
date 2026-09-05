/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { createReleaseMetadata } from "./release-metadata-lib.mjs"

const repositoryRoot = path.resolve(import.meta.dirname, "..")

async function createFixture(t) {
  const temporaryDirectory = await mkdtemp(path.join(os.tmpdir(), "platform-release-"))
  t.after(() => rm(temporaryDirectory, { recursive: true, force: true }))
  const fixtureRoot = path.join(temporaryDirectory, "repository")
  const migrationsDirectory = path.join(fixtureRoot, "apps", "api", "migrations", "versions")
  const metadataDirectory = path.join(temporaryDirectory, "metadata")
  const outputDirectory = path.join(temporaryDirectory, "output")
  await mkdir(migrationsDirectory, { recursive: true })
  await mkdir(metadataDirectory)
  await writeFile(path.join(fixtureRoot, "VERSION"), "0.1.0\n")
  await writeFile(path.join(migrationsDirectory, "0001_initial.py"), "revision: str = \"fixture_initial\"\ndown_revision: str | None = None\n")
  await writeFile(path.join(migrationsDirectory, "0002_head.py"), "revision: str = \"fixture_head\"\ndown_revision: str | None = \"fixture_initial\"\n")

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

  return {
    repositoryRoot: fixtureRoot,
    metadataDirectory,
    outputDirectory,
    envTemplatePath: path.join(repositoryRoot, "deploy", "single-lab", ".env.example"),
    releaseTag: "v0.1.0",
    gitCommit: "a".repeat(40),
    createdAt: "2026-08-14T00:00:00Z",
  }
}

test("release metadata binds every deployable component by digest", async (t) => {
  const options = await createFixture(t)
  const { manifest, manifestDigest } = await createReleaseMetadata(options)

  assert.equal(manifest.product_version, "0.1.0")
  assert.equal(manifest.database.revision, "fixture_head")
  assert.match(manifest.components.protocol_executor.deployment_reference, /@sha256:/)
  assert.match(manifestDigest, /^[0-9a-f]{64}$/)

  const renderedEnvironment = await readFile(path.join(options.outputDirectory, ".env.example"), "utf8")
  assert.match(renderedEnvironment, /^AIRALOGY_RELEASE_METADATA_REQUIRED=true$/mu)
  assert.match(renderedEnvironment, /^AIRALOGY_API_IMAGE=.+@sha256:/mu)
})

test("release metadata follows migration ancestry and rejects competing heads", async (t) => {
  const options = await createFixture(t)
  const migrationsDirectory = path.join(options.repositoryRoot, "apps", "api", "migrations", "versions")
  // The next revision deliberately sorts before its parent: lineage, not filename, selects the head.
  await writeFile(path.join(migrationsDirectory, "0000_followup.py"), "revision: str = \"fixture_next\"\ndown_revision: str | None = \"fixture_head\"\n")
  const { manifest } = await createReleaseMetadata(options)
  assert.equal(manifest.database.revision, "fixture_next")
  await writeFile(path.join(migrationsDirectory, "0003_branch.py"), "revision: str = \"fixture_branch\"\ndown_revision: str | None = \"fixture_head\"\n")
  await assert.rejects(createReleaseMetadata(options), /Expected one Alembic head, found 2/)
})

test("the checked-out release inputs produce a consistent manifest", async (t) => {
  const fixture = await createFixture(t)
  const version = (await readFile(path.join(repositoryRoot, "VERSION"), "utf8")).trim()
  const { manifest } = await createReleaseMetadata({ ...fixture, repositoryRoot, releaseTag: `v${version}` })
  assert.equal(manifest.product_version, version)
  assert.match(manifest.database.revision, /^[a-z0-9_]+$/)
  const releaseEnv = await readFile(path.join(fixture.outputDirectory, "release-manifest.env"), "utf8")
  assert.ok(releaseEnv.includes(`AIRALOGY_RELEASE_DATABASE_REVISION=${manifest.database.revision}\n`))
})

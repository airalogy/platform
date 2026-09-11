/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { checkReleaseStage } from "./check-release-stage.mjs"
import { createReleaseMetadata } from "./release-metadata-lib.mjs"

const repositoryRoot = path.resolve(import.meta.dirname, "..")

test("public release gate checks all exact images without logged-in Docker credentials", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "platform-public-gate-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const metadata = path.join(root, "image-metadata")
  await mkdir(metadata)
  const components = ["api", "web", "protocol-executor", "postgres"]
  for (const component of components) {
    await writeFile(path.join(metadata, `${component}.repository`), `ghcr.io/airalogy/platform-${component}\n`)
    await writeFile(path.join(metadata, `${component}.digest`), `sha256:${"a".repeat(64)}\n`)
  }
  const docker = `#!/bin/bash
set -eu
test "$DOCKER_CONFIG" != "$AUTHENTICATED_CONFIG"
test ! -e "$DOCKER_CONFIG/config.json"
test "$1 $2 $3" = "buildx imagetools inspect"
printf '%s\\n' "$4" >> "$GATE_CALLS"
if [[ "$4" == *"platform-$PRIVATE_COMPONENT@"* ]]; then exit 1; fi
`
  await writeFile(path.join(root, "docker"), docker, { mode: 0o755 })
  const workflow = await readFile(path.join(repositoryRoot, ".github/workflows/release.yml"), "utf8")
  const gate = workflow.split("      - name: Verify public installation access\n")[1]?.split("      - name: Create GitHub release\n")[0]
  assert.ok(gate, "public access must be checked before publication")
  const shell = gate.split("        run: |\n")[1].split("\n").map(line => line.replace(/^ {10}/, "")).join("\n")
  const calls = path.join(root, "calls")
  const env = { ...process.env, PATH: `${root}:${process.env.PATH}`, RUNNER_TEMP: root, AUTHENTICATED_CONFIG: "/synthetic-authenticated-config", GATE_CALLS: calls }
  const success = spawnSync("bash", ["-eu", "-o", "pipefail", "-c", shell], { cwd: root, env: { ...env, PRIVATE_COMPONENT: "none" }, encoding: "utf8" })
  assert.equal(success.status, 0, success.stderr)
  assert.equal((await readFile(calls, "utf8")).trim().split("\n").length, 4)
  const failure = spawnSync("bash", ["-eu", "-o", "pipefail", "-c", shell], { cwd: root, env: { ...env, PRIVATE_COMPONENT: "web" }, encoding: "utf8" })
  assert.notEqual(failure.status, 0)
  assert.match(failure.stdout, /not anonymously readable/)
})

test("release packaging rejects smoke secrets, runtime data and links", async (t) => {
  const stage = await mkdtemp(path.join(os.tmpdir(), "platform-release-stage-"))
  t.after(() => rm(stage, { recursive: true, force: true }))
  const allowed = new Set([".env.example", "VERSION"])
  await writeFile(path.join(stage, ".env.example"), "SECRET_KEY=replace-me\n")
  await writeFile(path.join(stage, "VERSION"), "0.1.0\n")
  assert.equal(await checkReleaseStage(stage, allowed), 2)
  await writeFile(path.join(stage, ".env"), "SECRET_KEY=private-test-value\n")
  await assert.rejects(checkReleaseStage(stage, allowed), /Unexpected release file: .env/)
  await rm(path.join(stage, ".env"))
  await mkdir(path.join(stage, "backups"))
  await assert.rejects(checkReleaseStage(stage, allowed), /Unexpected release directory: backups/)
  await rm(path.join(stage, "backups"), { recursive: true })
  await rm(path.join(stage, "VERSION"))
  await symlink(".env.example", path.join(stage, "VERSION"))
  await assert.rejects(checkReleaseStage(stage, allowed), /symbolic link: VERSION/)
})

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

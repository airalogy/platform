/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { execFileSync } from "node:child_process"
import { copyFile, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { delimiter, join } from "node:path"
import process from "node:process"
import test from "node:test"
import { computeTestImage } from "./compute-runner-integration.mjs"

test("E2E wrapper preserves exact test filters with or without pnpm's separator", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "platform-e2e-wrapper-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const script = join(root, "repository/tests/e2e/scripts/run.sh")
  const bin = join(root, "bin")
  await mkdir(join(root, "repository/tests/e2e/scripts"), { recursive: true })
  await mkdir(bin)
  await copyFile(new URL("../tests/e2e/scripts/run.sh", import.meta.url), script)
  // No Docker, browser or project data: record only the final forwarded arguments.
  await writeFile(join(bin, "docker"), "#!/usr/bin/env bash\nexit 0\n", { mode: 0o755 })
  await writeFile(join(bin, "corepack"), "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\"\n", { mode: 0o755 })
  for (const selected of [[], ["tests/e2e/specs/instrument-exploration.spec.ts"], ["--grep", "selected scenario", "--project", "chromium-owner"]]) {
    for (const prefix of [[], ["--"]]) {
      const output = execFileSync("bash", [script, ...prefix, ...selected], {
        encoding: "utf8",
        env: { ...process.env, PATH: `${bin}${delimiter}${process.env.PATH}` },
      })
      assert.deepEqual(output.trimEnd().split("\n"), ["pnpm", "exec", "playwright", "test", ...selected])
    }
  }
})

test("research wrapper pins real execution and preserves exact pytest arguments", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "platform-research-wrapper-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const scripts = join(root, "repository/scripts")
  const bin = join(root, "bin")
  await mkdir(scripts, { recursive: true })
  await mkdir(bin)
  for (const file of ["research-integration.mjs", "compute-runner-integration.mjs"])
    await copyFile(new URL(file, import.meta.url), join(scripts, file))
  // Transport-only wrapper test: no container or application service is opened.
  await writeFile(join(bin, "docker"), "#!/bin/sh\nexit 0\n", { mode: 0o755 })
  await writeFile(join(bin, "bash"), `#!/usr/bin/env node
process.stdout.write(JSON.stringify({args:process.argv.slice(2), engine:process.env.COMPUTE_ENGINE_TEST, image:process.env.COMPUTE_TEST_IMAGE, helper:process.env.COMPUTE_TEST_HELPER_IMAGE, backend:process.env.COMPUTE_TEST_BACKEND}))
`, { mode: 0o755 })
  for (const selected of [[], ["-q", "--tb=short"], ["-k", "generated_source or approval"]]) {
    for (const prefix of [[], ["--"]]) {
      const output = execFileSync(process.execPath, [join(scripts, "research-integration.mjs"), ...prefix, ...selected], {
        encoding: "utf8",
        env: { ...process.env, PATH: `${bin}${delimiter}${process.env.PATH}`, COMPUTE_ENGINE_TEST: "0", COMPUTE_TEST_IMAGE: "must-not-use:latest" },
      })
      assert.deepEqual(JSON.parse(output), {
        args: ["tests/e2e/scripts/research-integration.sh", ...selected],
        engine: "1",
        image: computeTestImage,
        helper: computeTestImage,
        backend: "docker",
      })
    }
  }
})

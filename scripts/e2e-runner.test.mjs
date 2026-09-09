/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { execFileSync } from "node:child_process"
import { copyFile, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { delimiter, join } from "node:path"
import process from "node:process"
import test from "node:test"

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

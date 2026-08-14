import { execFileSync } from "node:child_process"
import { mkdir, readFile, writeFile } from "node:fs/promises"
import { dirname, resolve } from "node:path"

const outputArgument = process.argv[2]
if (!outputArgument) {
  throw new Error("Usage: node scripts/write-build-info.mjs <output-file>")
}

const repositoryRoot = new URL("../", import.meta.url)
const version = (await readFile(new URL("../VERSION", import.meta.url), "utf8")).trim()

const runGit = (args, fallback = "") => {
  try {
    return execFileSync("git", args, {
      cwd: repositoryRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim()
  } catch {
    return fallback
  }
}

const commit = process.env.GIT_COMMIT?.trim() || runGit(["rev-parse", "HEAD"], "unknown")
const tag = process.env.GIT_TAG?.trim() || runGit(["describe", "--tags", "--exact-match"]) || null
const configuredDirty = process.env.BUILD_DIRTY?.trim()
const dirty =
  configuredDirty === undefined
    ? runGit(["status", "--porcelain"]) !== ""
    : configuredDirty === "true" || configuredDirty === "1"
const buildTime = process.env.BUILD_TIME?.trim() || new Date().toISOString()
const outputPath = resolve(process.cwd(), outputArgument)

await mkdir(dirname(outputPath), { recursive: true })
await writeFile(
  outputPath,
  `${JSON.stringify({ version, tag, commit, build_time: buildTime, dirty }, null, 2)}\n`,
  "utf8",
)

console.log(`Wrote Airalogy Platform ${version} build metadata to ${outputPath}`)

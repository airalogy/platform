import { execFileSync } from "node:child_process"
import { readdir } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

// An installation rehearsal must never turn its private configuration or data
// into public release attachments. Only tracked inputs and generated identity
// manifests belong in the deployment archive; do not follow symbolic links.
export async function checkReleaseStage(directory, allowedFiles) {
  let count = 0
  async function visit(relative = "") {
    for (const entry of await readdir(path.join(directory, relative), { withFileTypes: true })) {
      const name = relative ? `${relative}/${entry.name}` : entry.name
      if (entry.isSymbolicLink())
        throw new Error(`Release stage contains a symbolic link: ${name}`)
      if (entry.isDirectory()) {
        if (![...allowedFiles].some(file => file.startsWith(`${name}/`)))
          throw new Error(`Unexpected release directory: ${name}`)
        await visit(name)
      }
      else if (!entry.isFile() || !allowedFiles.has(name)) {
        throw new Error(`Unexpected release file: ${name}`)
      }
      else {
        count += 1
      }
    }
  }
  await visit()
  if (count === 0)
    throw new Error("Release stage is empty")
  return count
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (!process.argv[2])
    throw new Error("Usage: node scripts/check-release-stage.mjs <stage-directory>")
  const repositoryRoot = fileURLToPath(new URL("../", import.meta.url))
  const tracked = execFileSync("git", ["ls-files", "-z"], { cwd: repositoryRoot, encoding: "utf8" })
  const allowedFiles = new Set(tracked.split("\0").filter(Boolean))
  allowedFiles.add("deploy/single-lab/release-manifest.json")
  allowedFiles.add("deploy/single-lab/release-manifest.env")
  const count = await checkReleaseStage(path.resolve(process.argv[2]), allowedFiles)
  console.log(`Release stage contains ${count} approved files and no untracked runtime material.`)
}

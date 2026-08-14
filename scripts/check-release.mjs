import { execFileSync } from "node:child_process"
import { readFile } from "node:fs/promises"

const repositoryRoot = new URL("../", import.meta.url)
const version = (await readFile(new URL("../VERSION", import.meta.url), "utf8")).trim()
const expectedTag = `v${version}`
const suppliedTag = process.env.RELEASE_TAG?.trim() || process.argv[2]?.trim()

if (!suppliedTag) {
  throw new Error("A release tag is required")
}
if (suppliedTag !== expectedTag) {
  throw new Error(`Release tag ${suppliedTag} does not match VERSION ${version}`)
}

for (const changelogFile of ["CHANGELOG.md", "CHANGELOG.zh-CN.md"]) {
  const changelog = await readFile(new URL(`../${changelogFile}`, import.meta.url), "utf8")
  if (!changelog.includes(`## [${version}]`)) {
    throw new Error(`${changelogFile} does not declare release ${version}`)
  }
}

const trackedChanges = execFileSync("git", ["status", "--porcelain", "--untracked-files=no"], {
  cwd: repositoryRoot,
  encoding: "utf8",
}).trim()
if (trackedChanges) {
  throw new Error("Release verification requires a clean tracked worktree")
}

const exactTags = execFileSync("git", ["tag", "--points-at", "HEAD"], {
  cwd: repositoryRoot,
  encoding: "utf8",
})
  .trim()
  .split("\n")
  .filter(Boolean)
if (!exactTags.includes(suppliedTag)) {
  throw new Error(`HEAD is not tagged ${suppliedTag}`)
}

const tagObjectType = execFileSync("git", ["cat-file", "-t", suppliedTag], {
  cwd: repositoryRoot,
  encoding: "utf8",
}).trim()
if (tagObjectType !== "tag") {
  throw new Error(`Release tag ${suppliedTag} must be an annotated tag`)
}

console.log(`Airalogy Platform ${version} release metadata is valid for ${suppliedTag}`)

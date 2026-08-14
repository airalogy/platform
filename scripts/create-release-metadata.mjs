import { execFileSync } from "node:child_process"
import path from "node:path"
import { parseArgs } from "node:util"
import { createReleaseMetadata } from "./release-metadata-lib.mjs"

const { values } = parseArgs({
  options: {
    "metadata-directory": { type: "string" },
    "output-directory": { type: "string" },
    "env-template": { type: "string" },
    "release-tag": { type: "string" },
    "git-commit": { type: "string" },
    "created-at": { type: "string" },
  },
})

if (!values["metadata-directory"] || !values["output-directory"] || !values["env-template"]) {
  throw new Error("--metadata-directory, --output-directory, and --env-template are required")
}

const repositoryRoot = path.resolve(import.meta.dirname, "..")
const releaseTag = values["release-tag"]?.trim()
if (!releaseTag) {
  throw new Error("--release-tag is required")
}

const gitCommit =
  values["git-commit"]?.trim() ||
  execFileSync("git", ["rev-parse", "HEAD"], { cwd: repositoryRoot, encoding: "utf8" }).trim()
const createdAt = values["created-at"]?.trim() || new Date().toISOString()

const { manifest } = await createReleaseMetadata({
  repositoryRoot,
  metadataDirectory: path.resolve(values["metadata-directory"]),
  outputDirectory: path.resolve(values["output-directory"]),
  envTemplatePath: path.resolve(values["env-template"]),
  releaseTag,
  gitCommit,
  createdAt,
})

console.log(
  `Created Airalogy Platform ${manifest.product_version} release metadata for ${manifest.git_commit}`,
)

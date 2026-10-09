import { spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"
import { arch } from "node:os"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"

export const storageTestImage = "airalogy-platform-object-storage:e2e"
export const storageInputLabel = "io.airalogy.object-storage.inputs"
const context = fileURLToPath(new URL("../deploy/object-storage/", import.meta.url))

export function storageFingerprint(directory = context) {
  const hash = createHash("sha256")
  for (const file of ["Dockerfile", "build.sh", "sources.env"])
    hash.update(file).update("\0").update(readFileSync(resolve(directory, file))).update("\0")
  return hash.digest("hex")
}

export function prepareObjectStorage({ verifyOnly = false, run = spawnSync, architecture = arch() } = {}) {
  const fingerprint = storageFingerprint()
  const expectedArch = { x64: "amd64", arm64: "arm64" }[architecture]
  if (!expectedArch)
    throw new Error(`Unsupported object-storage test architecture: ${architecture}`)
  const inspected = run("docker", ["image", "inspect", storageTestImage], { encoding: "utf8", timeout: 30_000 })
  if (inspected.error)
    throw inspected.error
  if (inspected.status === 0) {
    const image = JSON.parse(inspected.stdout)[0]
    if (image?.Config?.Labels?.[storageInputLabel] === fingerprint && image.Architecture === expectedArch)
      return storageTestImage
  }
  if (verifyOnly)
    throw new Error("Object-storage image is missing or does not match this checkout and architecture")
  const result = run("docker", ["build", "--label", `${storageInputLabel}=${fingerprint}`, "--tag", storageTestImage, context], { stdio: "inherit" })
  if (result.error || result.status !== 0)
    throw new Error(`Object-storage build failed: ${result.error?.message || result.status}`)
  // Never accept a successful transport result without verifying its output.
  return prepareObjectStorage({ verifyOnly: true, run, architecture })
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const option = process.argv[2]
  if (process.argv.length > 3 || (option && !["--fingerprint", "--verify"].includes(option)))
    throw new Error("Usage: prepare-object-storage.mjs [--fingerprint|--verify]")
  if (option === "--fingerprint")
    console.log(storageFingerprint())
  else
    prepareObjectStorage({ verifyOnly: option === "--verify" })
}

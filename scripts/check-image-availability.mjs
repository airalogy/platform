import { spawnSync } from "node:child_process"
import { mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const root = fileURLToPath(new URL("../", import.meta.url))

export function imageReferences(source) {
  // Deliberately only accept the repository's static image/default syntax.
  // Do not evaluate .env, shell expressions, credentials or caller overrides.
  return [...source.matchAll(/^\s*image:\s*(\S+)\s*$/gm)].map(([, value]) => {
    const reference = value.replace(/^\$\{[A-Z_]+:-([^}]+)\}$/, "$1")
    if (!/^[a-z0-9][\w./:@-]+$/.test(reference) || reference.includes("://"))
      throw new Error(`Unsupported image reference: ${value}`)
    return reference
  })
}

export function checkImageAvailability(references, run = spawnSync) {
  if (!references.length)
    throw new Error("No external images selected; refusing an empty availability check")
  const config = mkdtempSync(join(tmpdir(), "platform-anonymous-registry-"))
  try {
    for (const reference of new Set(references)) {
      console.log(`[images] Checking anonymous registry access: ${reference}`)
      // Inspect the registry's raw index, not every platform's image config.
      // Actual artifact builds/pulls remain required downstream.
      const result = run("docker", ["--config", config, "buildx", "imagetools", "inspect", "--raw", reference], {
        encoding: "utf8",
        timeout: 30_000,
        killSignal: "SIGKILL",
        maxBuffer: 4 * 1024 * 1024,
        env: { ...process.env, DOCKER_CONFIG: config, DOCKER_AUTH_CONFIG: "" },
      })
      if (result.error || result.status !== 0)
        throw new Error(`External image unavailable: ${reference}. Cold CI/install cannot use a local cached image. Resolve registry access before long tests or publication. ${result.error?.message || result.stderr?.trim() || "Registry check failed"}`)
      const manifest = JSON.parse(result.stdout)
      if (manifest.schemaVersion !== 2 || (!manifest.manifests?.length && !manifest.layers?.length))
        throw new Error(`Registry did not return a usable image manifest: ${reference}`)
    }
  }
  finally {
    rmSync(config, { recursive: true, force: true })
  }
}

export function externalBuildInputs(repositoryRoot = root) {
  const compose = readFileSync(join(repositoryRoot, "tests/e2e/compose.yml"), "utf8")
  const references = imageReferences(compose)
  const defaults = readFileSync(join(repositoryRoot, "deploy/single-lab/.env.example"), "utf8")
  const external = [...defaults.matchAll(/^(?:MINIO_IMAGE|MINIO_MC_IMAGE|REDIS_IMAGE)=(.+)$/gm)].map(([, ref]) => ref)
  if (references.length !== 3 || external.length !== 3 || !compose.includes("context: ../../deploy/object-storage"))
    throw new Error("Update the external-image preflight when changing the service inventory")
  const dockerfile = readFileSync(join(repositoryRoot, "deploy/object-storage/Dockerfile"), "utf8")
  const bases = [...dockerfile.matchAll(/^FROM (?:--platform=\$BUILDPLATFORM )?(\S+)/gm)].map(([, ref]) => ref).filter(ref => ref !== "source")
  if (bases.length !== 2 || bases.some(ref => !/@sha256:[a-f0-9]{64}$/.test(ref)))
    throw new Error("Object-storage build bases must be pinned by digest")
  const version = readFileSync(join(repositoryRoot, "VERSION"), "utf8").trim()
  const built = new Set(["airalogy-platform-object-storage:e2e", `airalogy-platform-object-storage:${version}`])
  const refs = [...references, ...external]
  if (refs.filter(ref => built.has(ref)).length !== 4)
    throw new Error("Expected source-built object storage in both test and release defaults")
  return [...refs.filter(ref => !built.has(ref)), ...bases]
}

export async function checkStorageSourceAvailability(request = fetch) {
  const lock = readFileSync(join(root, "deploy/object-storage/sources.env"), "utf8")
  for (const name of ["MINIO", "MC"]) {
    const commit = new RegExp(`^${name}_COMMIT=([a-f0-9]{40})$`, "m").exec(lock)?.[1]
    if (!commit)
      throw new Error(`Missing pinned ${name} source commit`)
    const response = await request(`https://codeload.github.com/minio/${name.toLowerCase()}/tar.gz/${commit}`, { method: "HEAD", signal: AbortSignal.timeout(30_000) })
    if (!response.ok)
      throw new Error(`${name} source unavailable: HTTP ${response.status}`)
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv.length !== 2)
    throw new Error("Usage: node scripts/check-image-availability.mjs")
  checkImageAvailability(externalBuildInputs())
  await checkStorageSourceAvailability()
}

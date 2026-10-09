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
      const result = run("docker", ["--config", config, "manifest", "inspect", reference], {
        encoding: "utf8",
        timeout: 30_000,
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

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv.length !== 2)
    throw new Error("Usage: node scripts/check-image-availability.mjs")
  const references = imageReferences(readFileSync(join(root, "tests/e2e/compose.yml"), "utf8"))
  // Release dependencies must remain publicly installable as well as testable.
  const defaults = readFileSync(join(root, "deploy/single-lab/.env.example"), "utf8")
  const external = [...defaults.matchAll(/^(?:MINIO_IMAGE|MINIO_MC_IMAGE|REDIS_IMAGE)=(.+)$/gm)].map(([, ref]) => ref)
  if (references.length !== 3 || external.length !== 3)
    throw new Error("Update the external-image preflight when changing the service inventory")
  checkImageAvailability([...references.filter(ref => ref.includes("minio")), ...references, ...external])
}

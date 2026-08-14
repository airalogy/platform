import { createHash } from "node:crypto"
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises"
import path from "node:path"

const digestPattern = /^sha256:[0-9a-f]{64}$/
const commitPattern = /^[0-9a-f]{40}$/

const readRequiredText = async filePath => {
  const value = (await readFile(filePath, "utf8")).trim()
  if (!value) {
    throw new Error(`${filePath} is empty`)
  }
  return value
}

const assertDigest = (value, label) => {
  if (!digestPattern.test(value)) {
    throw new Error(`${label} must be a sha256 digest`)
  }
}

const assertRepository = (value, label) => {
  if (!/^[a-z0-9][a-z0-9._/-]*$/i.test(value) || value.includes("@") || value.endsWith("/")) {
    throw new Error(`${label} must be an untagged container repository`)
  }
}

const replaceEnvValue = (source, key, value) => {
  const linePattern = new RegExp(`^${key}=.*$`, "mu")
  if (!linePattern.test(source)) {
    throw new Error(`Deployment environment template is missing ${key}`)
  }
  return source.replace(linePattern, `${key}=${value}`)
}

const latestAlembicRevision = async repositoryRoot => {
  const migrationsDirectory = path.join(repositoryRoot, "apps", "api", "migrations", "versions")
  const entries = await readdir(migrationsDirectory, { withFileTypes: true })
  const revisions = new Set()
  const parents = new Set()

  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".py")) {
      continue
    }
    const source = await readFile(path.join(migrationsDirectory, entry.name), "utf8")
    const revision = /^revision:\s*str\s*=\s*"([^"]+)"$/mu.exec(source)?.[1]
    const parent = /^down_revision:\s*str\s*\|\s*None\s*=\s*"([^"]+)"$/mu.exec(source)?.[1]
    if (revision) {
      revisions.add(revision)
    }
    if (parent) {
      parents.add(parent)
    }
  }

  const heads = [...revisions].filter(revision => !parents.has(revision)).sort()
  if (heads.length !== 1) {
    throw new Error(`Expected one Alembic head, found ${heads.length}: ${heads.join(", ")}`)
  }
  return heads[0]
}

const readImageMetadata = async (metadataDirectory, component) => {
  const repository = await readRequiredText(path.join(metadataDirectory, `${component}.repository`))
  const digest = await readRequiredText(path.join(metadataDirectory, `${component}.digest`))
  assertRepository(repository, `${component} repository`)
  assertDigest(digest, `${component} digest`)
  return { repository, digest }
}

const componentMetadata = ({ repository, digest }, version) => ({
  repository,
  digest,
  tagged_reference: `${repository}:${version}`,
  deployment_reference: `${repository}:${version}@${digest}`,
})

const serializeReleaseEnv = (manifest, manifestDigest) => {
  const values = {
    AIRALOGY_RELEASE_SCHEMA_VERSION: manifest.schema_version,
    AIRALOGY_RELEASE_MANIFEST_SHA256: manifestDigest,
    AIRALOGY_RELEASE_PRODUCT_VERSION: manifest.product_version,
    AIRALOGY_RELEASE_TAG: manifest.release_tag,
    AIRALOGY_RELEASE_COMMIT: manifest.git_commit,
    AIRALOGY_RELEASE_DATABASE_REVISION: manifest.database.revision,
    AIRALOGY_RELEASE_API_IMAGE: manifest.components.api.deployment_reference,
    AIRALOGY_RELEASE_API_TAGGED_IMAGE: manifest.components.api.tagged_reference,
    AIRALOGY_RELEASE_API_DIGEST: manifest.components.api.digest,
    AIRALOGY_RELEASE_WEB_IMAGE: manifest.components.web.deployment_reference,
    AIRALOGY_RELEASE_WEB_TAGGED_IMAGE: manifest.components.web.tagged_reference,
    AIRALOGY_RELEASE_WEB_DIGEST: manifest.components.web.digest,
    AIRALOGY_RELEASE_PROTOCOL_EXECUTOR_IMAGE:
      manifest.components.protocol_executor.deployment_reference,
    AIRALOGY_RELEASE_PROTOCOL_EXECUTOR_TAGGED_IMAGE:
      manifest.components.protocol_executor.tagged_reference,
    AIRALOGY_RELEASE_PROTOCOL_EXECUTOR_DIGEST: manifest.components.protocol_executor.digest,
    AIRALOGY_RELEASE_POSTGRES_IMAGE: manifest.components.postgres.deployment_reference,
    AIRALOGY_RELEASE_POSTGRES_TAGGED_IMAGE: manifest.components.postgres.tagged_reference,
    AIRALOGY_RELEASE_POSTGRES_DIGEST: manifest.components.postgres.digest,
  }
  return `${Object.entries(values)
    .map(([key, value]) => `${key}=${value}`)
    .join("\n")}\n`
}

export const createReleaseMetadata = async ({
  repositoryRoot,
  metadataDirectory,
  outputDirectory,
  envTemplatePath,
  releaseTag,
  gitCommit,
  createdAt,
}) => {
  const version = await readRequiredText(path.join(repositoryRoot, "VERSION"))
  if (releaseTag !== `v${version}`) {
    throw new Error(`Release tag ${releaseTag} does not match VERSION ${version}`)
  }
  if (!commitPattern.test(gitCommit)) {
    throw new Error("Git commit must be a complete 40-character SHA")
  }
  if (Number.isNaN(Date.parse(createdAt))) {
    throw new Error("Release creation time must be an ISO-compatible timestamp")
  }

  const [api, web, protocolExecutor, postgres, databaseRevision, envTemplate] = await Promise.all([
    readImageMetadata(metadataDirectory, "api"),
    readImageMetadata(metadataDirectory, "web"),
    readImageMetadata(metadataDirectory, "protocol-executor"),
    readImageMetadata(metadataDirectory, "postgres"),
    latestAlembicRevision(repositoryRoot),
    readFile(envTemplatePath, "utf8"),
  ])

  const manifest = {
    schema_version: 1,
    product: "Airalogy Platform Community Edition",
    product_version: version,
    release_tag: releaseTag,
    git_commit: gitCommit,
    created_at: new Date(createdAt).toISOString(),
    database: {
      engine: "PostgreSQL 16 with pgvector and zhparser",
      migration_system: "Alembic",
      revision: databaseRevision,
    },
    components: {
      api: componentMetadata(api, version),
      web: componentMetadata(web, version),
      protocol_executor: componentMetadata(protocolExecutor, version),
      postgres: componentMetadata(postgres, version),
    },
  }
  const manifestJson = `${JSON.stringify(manifest, null, 2)}\n`
  const manifestDigest = createHash("sha256").update(manifestJson).digest("hex")
  const releaseEnv = serializeReleaseEnv(manifest, manifestDigest)

  let renderedEnv = envTemplate
  const replacements = {
    PLATFORM_VERSION: version,
    AIRALOGY_API_IMAGE: manifest.components.api.deployment_reference,
    AIRALOGY_WEB_IMAGE: manifest.components.web.deployment_reference,
    AIRALOGY_PROTOCOL_EXECUTOR_IMAGE: manifest.components.protocol_executor.deployment_reference,
    AIRALOGY_POSTGRES_IMAGE: manifest.components.postgres.deployment_reference,
    AIRALOGY_RELEASE_METADATA_REQUIRED: "true",
    GIT_TAG: manifest.release_tag,
    GIT_COMMIT: manifest.git_commit,
    BUILD_TIME: manifest.created_at,
    BUILD_DIRTY: "false",
    AIRALOGY_RELEASE_MANIFEST_SHA256: manifestDigest,
  }
  for (const [key, value] of Object.entries(replacements)) {
    renderedEnv = replaceEnvValue(renderedEnv, key, value)
  }

  await mkdir(outputDirectory, { recursive: true })
  await Promise.all([
    writeFile(path.join(outputDirectory, "release-manifest.json"), manifestJson),
    writeFile(path.join(outputDirectory, "release-manifest.env"), releaseEnv),
    writeFile(path.join(outputDirectory, ".env.example"), renderedEnv),
  ])

  return { manifest, manifestDigest }
}

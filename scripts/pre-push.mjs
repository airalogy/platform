import { execFileSync, spawnSync } from "node:child_process"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"

const ZERO_SHA = "0".repeat(40)
const AI_E2E_SPEC = "tests/e2e/specs/ai-protocol-editor.spec.ts"

const checks = {
  lint: {
    id: "lint",
    label: "workspace lint",
    command: "corepack",
    args: ["pnpm", "lint"],
  },
  types: {
    id: "types",
    label: "workspace type check",
    command: "corepack",
    args: ["pnpm", "type-check"],
  },
  apiCompile: {
    id: "api-compile",
    label: "API entrypoint compile check",
    command: "corepack",
    args: ["pnpm", "api:check"],
  },
  apiTests: {
    id: "api-tests",
    label: "API unit tests",
    command: "corepack",
    args: ["pnpm", "api:test"],
  },
  researchIntegration: {
    id: "research-integration",
    label: "research API and persistent-worker integration",
    command: "corepack",
    args: ["pnpm", "research:integration"],
  },
  gatewayTests: {
    id: "gateway-tests",
    label: "Instrument Gateway tests",
    command: "corepack",
    args: ["pnpm", "gateway:test"],
  },
  computeRunnerTests: {
    id: "compute-runner-tests",
    label: "Compute Runner tests",
    command: "corepack",
    args: ["pnpm", "compute-runner:test"],
  },
  docs: {
    id: "docs",
    label: "documentation production build",
    command: "corepack",
    args: ["pnpm", "docs:build"],
    env: { DOCS_BASE: "/docs/" },
  },
  aiE2e: {
    id: "ai-e2e",
    label: "AI capability browser E2E",
    command: "corepack",
    args: ["pnpm", "e2e", "--", AI_E2E_SPEC],
  },
  fullE2e: {
    id: "full-e2e",
    label: "full browser E2E",
    command: "corepack",
    args: ["pnpm", "e2e"],
  },
}

const DOCS_FILES = new Set([
  ".github/workflows/docs.yml",
  "package.json",
  "pnpm-lock.yaml",
  "pnpm-workspace.yaml",
])

const FULL_E2E_FILES = new Set([
  ".github/workflows/e2e.yml",
  "package.json",
  "playwright.config.ts",
  "pnpm-lock.yaml",
  "pnpm-workspace.yaml",
])

const AI_E2E_FILES = new Set([
  "apps/api/app/config.py",
  "apps/api/app/routers/instance.py",
  "apps/api/app/services/chat_models.py",
  "apps/web/src/router/guard/instance.ts",
  "apps/web/src/service/api/instance.ts",
])

const AI_E2E_PREFIXES = [
  "apps/web/src/components/apply-steps/",
  "apps/web/src/store/modules/instance/",
  "apps/web/src/views/editor/",
]

const GATEWAY_FILES = new Set([".github/workflows/instrument-gateway.yml"])
const COMPUTE_RUNNER_FILES = new Set([".github/workflows/compute-runner.yml"])

function hasPath(files, exactFiles, prefixes = []) {
  return files.some(
    file => exactFiles.has(file) || prefixes.some(prefix => file.startsWith(prefix)),
  )
}

export function buildCheckPlan(files, fullRequested = false) {
  const plan = [checks.lint, checks.types, checks.apiCompile]

  if (files.some(file => file.startsWith("apps/api/"))) {
    plan.push(checks.apiTests)
  }
  if (fullRequested || files.some(file =>
    /^apps\/api\/(?:app\/(?:models|routers|services)\/research|tests\/test_research)/.test(file)
    || [
      "apps/api/app/services/persistent_jobs.py",
      "apps/api/app/services/resource_job_worker.py",
      "apps/api/app/models/base.py",
      "apps/api/app/database.py",
      "tests/e2e/scripts/api-env.sh",
      "tests/e2e/scripts/research-integration.sh",
      ".github/workflows/research-integration.yml",
    ].includes(file),
  )) {
    plan.push(checks.researchIntegration)
  }

  if (hasPath(files, GATEWAY_FILES, ["apps/instrument-gateway/"])) {
    plan.push(checks.gatewayTests)
  }

  if (hasPath(files, COMPUTE_RUNNER_FILES, ["apps/compute-runner/"])) {
    plan.push(checks.computeRunnerTests)
  }

  if (hasPath(files, DOCS_FILES, ["docs/"])) {
    plan.push(checks.docs)
  }

  const needsFullE2e = fullRequested || hasPath(files, FULL_E2E_FILES, ["tests/e2e/"])
  if (needsFullE2e) {
    plan.push(checks.fullE2e)
  }
  else if (hasPath(files, AI_E2E_FILES, AI_E2E_PREFIXES)) {
    plan.push(checks.aiE2e)
  }

  return plan
}

function runGit(args) {
  return execFileSync("git", args, { encoding: "utf8" }).trim()
}

function diffFiles(from, to) {
  const output = runGit(["diff", "--name-only", `${from}..${to}`])
  return output ? output.split("\n") : []
}

function baseForNewBranch(localSha) {
  try {
    return runGit(["merge-base", localSha, "origin/main"])
  }
  catch {
    return runGit(["rev-list", "--max-parents=0", localSha]).split("\n")[0]
  }
}

function filesFromPushInput(input) {
  const files = new Set()
  const updates = input.trim().split("\n").filter(Boolean)

  for (const update of updates) {
    const [, localSha, , remoteSha] = update.trim().split(/\s+/)
    if (!localSha || localSha === ZERO_SHA) {
      continue
    }

    const base = remoteSha && remoteSha !== ZERO_SHA ? remoteSha : baseForNewBranch(localSha)
    for (const file of diffFiles(base, localSha)) {
      files.add(file)
    }
  }

  return [...files].sort()
}

function filesFromUpstream() {
  try {
    const upstream = runGit(["rev-parse", "--verify", "@{upstream}"])
    return diffFiles(upstream, "HEAD").sort()
  }
  catch {
    const root = runGit(["rev-list", "--max-parents=0", "HEAD"]).split("\n")[0]
    return diffFiles(root, "HEAD").sort()
  }
}

function readPushInput() {
  if (process.stdin.isTTY) {
    return ""
  }
  return readFileSync(0, "utf8")
}

function runCheck(check) {
  console.log(`\n[pre-push] ${check.label}`)
  const result = spawnSync(check.command, check.args, {
    cwd: process.cwd(),
    env: { ...process.env, ...check.env },
    stdio: "inherit",
  })

  if (result.error) {
    throw result.error
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1)
  }
}

function main() {
  const input = readPushInput()
  const files = input.trim() ? filesFromPushInput(input) : filesFromUpstream()
  const fullRequested = process.argv.includes("--full")
  const plan = buildCheckPlan(files, fullRequested)

  console.log(
    `[pre-push] ${files.length} pushed file(s); checks: ${plan.map(check => check.id).join(", ")}`,
  )
  for (const check of plan) {
    runCheck(check)
  }
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : ""
if (fileURLToPath(import.meta.url) === invokedPath) {
  main()
}

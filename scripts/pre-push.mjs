import { execFileSync, spawnSync } from "node:child_process"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { checkNodeRuntime } from "./check-node-runtime.mjs"

const ZERO_SHA = "0".repeat(40)
const AI_E2E_SPEC = "tests/e2e/specs/ai-protocol-editor.spec.ts"

export const checks = {
  ci: {
    id: "ci-config",
    label: "workflow syntax, CI preparation and check-selection regression tests",
    command: "corepack",
    args: ["pnpm", "ci:check"],
  },
  version: {
    id: "version",
    label: "product and component version consistency",
    command: "corepack",
    args: ["pnpm", "version:check"],
  },
  gatewayCli: {
    id: "gateway-cli",
    label: "real GitHub CLI arguments and offline rejection (no credentials or publication)",
    command: "python3",
    args: ["-m", "unittest", "discover", "-s", "apps/instrument-gateway/tests", "-p", "test_bootstrap.py"],
    env: { PYTHONPATH: "apps/instrument-gateway/src", RUN_BOOTSTRAP_ATTESTATION_TESTS: "1" },
  },
  apiLock: {
    id: "api-lock",
    label: "API locked dependencies",
    command: "uv",
    args: ["--directory", "apps/api", "lock", "--check"],
  },
  gatewayLock: {
    id: "gateway-lock",
    label: "Gateway locked dependencies",
    command: "uv",
    args: ["--directory", "apps/instrument-gateway", "lock", "--check"],
  },
  computeLock: {
    id: "compute-lock",
    label: "Compute Runner locked dependencies",
    command: "uv",
    args: ["--directory", "apps/compute-runner", "lock", "--check"],
  },
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
  releaseMetadata: {
    id: "release-metadata",
    label: "release metadata and migration-head checks",
    command: "corepack",
    args: ["pnpm", "release:metadata:test"],
  },
  deploymentIdentity: {
    id: "deployment-identity",
    label: "deployment identity and release archive safety",
    command: "corepack",
    args: ["pnpm", "deployment:identity:test"],
  },
  instrumentContract: {
    id: "instrument-contract",
    label: "generated instrument contract consistency",
    command: "corepack",
    args: ["pnpm", "gateway:contract:check"],
  },
  researchIntegration: {
    id: "research-integration",
    label: "research API and persistent-worker integration",
    command: "corepack",
    args: ["pnpm", "research:integration"],
    env: { RUN_INSTRUMENT_NATIVE_JOB_TESTS: "0" },
  },
  gatewayTests: {
    id: "gateway-tests",
    label: "Instrument Gateway tests",
    command: "corepack",
    args: ["pnpm", "gateway:test"],
  },
  interfaceTests: {
    id: "interface-tests",
    label: "bounded browser interface and private evidence tests",
    command: "corepack",
    args: ["pnpm", "gateway:interface-test"],
    env: { RUN_INTERFACE_NATIVE_TESTS: "0", RUN_INTERFACE_NATIVE_BUILD_TESTS: "0" },
  },
  interfaceDemo: {
    id: "interface-demo",
    label: "owned browser rehearsal compatibility",
    command: "corepack",
    args: ["pnpm", "gateway:gui-demo"],
  },
  nativeBuildTests: {
    id: "native-build-tests",
    label: "macOS native build and installed-SDK integrity checks (no app launch)",
    command: "node",
    args: ["--test", "apps/instrument-interface/tests/native.test.mjs"],
    env: { RUN_INTERFACE_NATIVE_BUILD_TESTS: "1", RUN_INTERFACE_NATIVE_TESTS: "0", RUN_INSTRUMENT_NATIVE_JOB_TESTS: "0" },
  },
  computeRunnerTests: {
    id: "compute-runner-tests",
    label: "Compute Runner tests",
    command: "corepack",
    args: ["pnpm", "compute-runner:test"],
  },
  computeEngine: {
    id: "compute-engine",
    label: "real isolated Compute engine and private input/output acceptance",
    command: "node",
    args: ["scripts/compute-runner-integration.mjs"],
  },
  docs: {
    id: "docs",
    label: "documentation production build",
    command: "corepack",
    args: ["pnpm", "docs:build"],
    env: { DOCS_BASE: "/docs/" },
  },
  build: {
    id: "build",
    label: "production Web and bundled documentation build",
    command: "corepack",
    args: ["pnpm", "build"],
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
    command: "node",
    args: ["scripts/e2e-matrix.mjs"],
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
  "scripts/e2e-matrix.mjs",
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

const GATEWAY_FILES = new Set([
  ".github/workflows/instrument-gateway.yml",
  "apps/api/app/services/instrument_adapter_contract.py",
  "apps/api/app/services/instrument_package_contract.py",
  "apps/api/app/services/instrument_installation_contract.py",
  "apps/api/app/services/instrument_activation_contract.py",
  "apps/api/app/services/instrument_output_contract.py",
  "apps/api/app/services/instrument_authoring_contract.py",
  "scripts/sync-instrument-contract.mjs",
  "scripts/instrument-authoring-example.mjs",
])
const COMPUTE_RUNNER_FILES = new Set([".github/workflows/compute-runner.yml", "scripts/compute-runner-integration.mjs"])

function hasPath(files, exactFiles, prefixes = []) {
  return files.some(
    file => exactFiles.has(file) || prefixes.some(prefix => file.startsWith(prefix)),
  )
}

export function buildCheckPlan(files, fullRequested = false, hostPlatform = process.platform) {
  if (fullRequested || files.some(file => file === ".node-version" || file.startsWith("scripts/check-node-runtime"))) {
    // Full means every registered local gate, except the focused E2E subset
    // (already in full-e2e) and macOS compilation on a non-macOS host.
    return Object.values(checks).filter(check => check.id !== "ai-e2e"
      && (hostPlatform === "darwin" || check.id !== "native-build-tests"))
  }
  const plan = [checks.version, checks.lint, checks.types, checks.apiCompile]
  const toolingChanged = files.some(file => file.startsWith(".github/")
    || /^scripts\/(?:check-node-runtime|actionlint|prepare-instrument-ci|pre-push|e2e-(?:runner|matrix))/.test(file)
    || file.startsWith(".husky/")
    || [".node-version", "package.json", "pnpm-workspace.yaml", "pnpm-lock.yaml"].includes(file))
  if (toolingChanged)
    plan.unshift(checks.ci)
  for (const [directory, check] of [["api", checks.apiLock], ["instrument-gateway", checks.gatewayLock], ["compute-runner", checks.computeLock]]) {
    if (files.some(file => [`apps/${directory}/pyproject.toml`, `apps/${directory}/uv.lock`, "VERSION", ".github/workflows/release.yml"].includes(file)))
      plan.push(check)
  }

  if (files.some(file =>
    ["VERSION", ".github/workflows/release.yml", "scripts/check-version.mjs", "scripts/create-release-metadata.mjs", "scripts/check-release-stage.mjs", "scripts/deployment-identity.test.sh"].includes(file)
    || file.startsWith("apps/api/migrations/")
    || file.startsWith("scripts/release-")
    || file.startsWith("deploy/"),
  )) {
    plan.push(checks.releaseMetadata)
    plan.push(checks.deploymentIdentity)
  }

  if (files.some(file => file.startsWith("apps/api/"))) {
    plan.push(checks.apiTests)
  }
  if (files.some(file =>
    /^apps\/api\/(?:app\/(?:models|routers|services)\/research|tests\/test_research)/.test(file)
    || /^apps\/api\/(?:app\/(?:models|routers|services)\/workflow|tests\/test_workflow)/.test(file)
    || /^apps\/api\/(?:app\/(?:models|routers|services)\/(?:analys(?:is|es)|record_analyses)|tests\/(?:test_analysis|test_record_analysis))/.test(file)
    || /^apps\/api\/(?:app\/(?:models|routers|services)\/instrument|tests\/test_instrument)/.test(file)
    || /^apps\/api\/tests\/(?:activation|instrument_output|http_read|authoring|exploration)_acceptance\.py$/.test(file)
    || /^apps\/instrument-gateway\/(?:src|tests|examples)\//.test(file)
    || /^apps\/compute-runner\/(?:src|tests)\//.test(file)
    || file.startsWith("apps/instrument-interface/")
    || /^apps\/api\/migrations\/versions\/\d+_(?:instrument|analysis|workflow)/.test(file)
    || [
      "apps/api/app/services/persistent_jobs.py",
      "apps/api/app/services/resource_job_worker.py",
      "apps/api/app/models/airalogy_file.py",
      "apps/api/app/routers/airalogy_files.py",
      "apps/api/app/routers/airalogy_api.py",
      "apps/api/app/routers/records.py",
      "apps/api/app/routers/record_exports.py",
      "apps/api/app/routers/aira_imports.py",
      "apps/api/app/services/record_exports.py",
      "apps/api/app/routers/labs.py",
      "apps/api/app/libs/lab_force_delete.py",
      "apps/api/tests/test_lab_workflow_file_cleanup.py",
      "apps/api/tests/test_lab_workflow_file_cleanup_postgres.py",
      "apps/api/app/models/base.py",
      "apps/api/app/database.py",
      "tests/e2e/scripts/api-env.sh",
      "tests/e2e/scripts/research-integration.sh",
      "scripts/research-integration.mjs",
      "scripts/compute-runner-integration.mjs",
      ".github/workflows/research-integration.yml",
      "scripts/instrument-interface-example.mjs",
      "scripts/instrument-interface-worker-example.mjs",
    ].includes(file),
  )) {
    plan.push(checks.researchIntegration)
  }

  const gatewayChanged = hasPath(files, GATEWAY_FILES, ["apps/instrument-gateway/"])
  const interfaceChanged = hasPath(files, new Set([
    ".github/workflows/instrument-interface.yml",
    "scripts/instrument-gui-demo.mjs",
    "scripts/instrument-interface-example.mjs",
    "scripts/instrument-interface-worker-example.mjs",
    "scripts/sync-instrument-contract.mjs",
    "apps/instrument-gateway/examples/simulated-reader.html",
    "apps/api/app/services/instrument_survey.schema.json",
    "apps/api/app/services/instrument_exploration.schema.json",
    "apps/api/app/services/instrument_application_selection.schema.json",
    "package.json",
    "pnpm-workspace.yaml",
    "pnpm-lock.yaml",
  ]), ["apps/instrument-interface/", "apps/instrument-gateway/src/", "apps/instrument-gateway/tests/native_read"])
  if (gatewayChanged || interfaceChanged || files.some(file => file.startsWith("scripts/prepare-instrument-ci") || file === ".github/workflows/release.yml"))
    plan.splice(toolingChanged ? 2 : 1, 0, checks.gatewayCli)
  if (gatewayChanged || interfaceChanged)
    plan.push(checks.instrumentContract)
  if (gatewayChanged) {
    plan.push(checks.gatewayTests)
  }

  if (interfaceChanged) {
    plan.push(checks.interfaceTests)
    plan.push(checks.interfaceDemo)
  }

  if (hostPlatform === "darwin" && (interfaceChanged || files.some(file =>
    /^apps\/instrument-interface\/(?:src\/(?:native|macos\/|worker-runtime)|tests\/native)/.test(file)
    || file === "apps/instrument-gateway/src/airalogy_instrument_gateway/interface_process.py"
    || /^apps\/instrument-gateway\/tests\/native_read/.test(file),
  ))) {
    plan.push(checks.nativeBuildTests)
  }

  if (hasPath(files, COMPUTE_RUNNER_FILES, ["apps/compute-runner/"])) {
    plan.push(checks.computeRunnerTests)
  }
  if (hasPath(files, COMPUTE_RUNNER_FILES, ["apps/compute-runner/"])
    || files.some(file => /^apps\/api\/app\/(?:routers|services)\/(?:analysis_compute|research_compute_jobs)/.test(file))) {
    plan.push(checks.computeEngine)
  }

  if (hasPath(files, DOCS_FILES, ["docs/"])) {
    plan.push(checks.docs)
  }
  if (files.some(file => file.startsWith("apps/web/") || file.startsWith("packages/")
    || ["package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", "deploy/single-lab/web.Dockerfile"].includes(file))) {
    plan.push(checks.build)
  }

  const needsFullE2e = hasPath(files, FULL_E2E_FILES, ["tests/e2e/"])
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

export function runCheck(check) {
  console.log(`\n[pre-push] ${check.label}`)
  const result = spawnSync(check.command, check.args, {
    cwd: process.cwd(),
    env: { ...process.env, RUN_INTERFACE_NATIVE_TESTS: "0", RUN_INTERFACE_NATIVE_BUILD_TESTS: "0", RUN_INSTRUMENT_NATIVE_JOB_TESTS: "0", ...check.env },
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
  checkNodeRuntime()
  // CI invokes these same gates directly, without reading Git hook stdin or
  // guessing a diff. Unknown identifiers/flags fail rather than silently skip.
  if (process.argv[2] === "--check") {
    const check = Object.values(checks).find(item => item.id === process.argv[3])
    if (!check || process.argv.length !== 4)
      throw new Error("Specify one registered check ID after --check")
    runCheck(check)
    return
  }
  if (process.argv.slice(2).some(arg => !["--full", "--plan"].includes(arg)))
    throw new Error("Usage: pre-push.mjs [--full] [--plan], or --check <id>")
  const input = readPushInput()
  const files = input.trim() ? filesFromPushInput(input) : filesFromUpstream()
  const fullRequested = process.argv.includes("--full")
  const plan = buildCheckPlan(files, fullRequested)

  console.log(
    `[pre-push] ${files.length} pushed file(s); checks: ${plan.map(check => check.id).join(", ")}`,
  )
  if (process.argv.includes("--plan"))
    return
  for (const check of plan) {
    runCheck(check)
  }
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : ""
if (fileURLToPath(import.meta.url) === invokedPath) {
  main()
}

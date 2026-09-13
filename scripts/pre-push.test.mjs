/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { readFileSync } from "node:fs"
import test from "node:test"
import { load } from "js-yaml"
import { buildCheckPlan, checks } from "./pre-push.mjs"

const ids = (files, full = false, host = "linux") => buildCheckPlan(files, full, host).map(check => check.id)
function includes(files, expected, host = "linux") {
  const actual = ids(files, false, host)
  for (const id of expected)
    assert.ok(actual.includes(id), `${files}: missing ${id}; selected ${actual}`)
  assert.equal(new Set(actual).size, actual.length, "checks should run only once")
}

test("ordinary docs and AI edits retain focused checks", () => {
  assert.deepEqual(ids(["docs/guide/getting-started.md"]), ["version", "lint", "types", "api-compile", "docs"])
  includes(["apps/web/src/store/modules/instance/index.ts"], ["ai-e2e", "build"])
  assert.ok(!ids(["apps/web/src/store/modules/instance/index.ts"]).includes("full-e2e"))
  includes(["apps/api/app/config.py"], ["api-tests", "ai-e2e"])
  includes(["tests/e2e/scripts/start-api.sh"], ["full-e2e"])
  assert.ok(!ids(["README.md"]).includes("gateway-cli"))
})

test("CI and hook changes select real tooling regressions before expensive checks", () => {
  for (const file of ["scripts/prepare-instrument-ci.mjs", "scripts/prepare-instrument-ci.test.mjs", "scripts/actionlint.mjs", "scripts/actionlint.test.mjs", "scripts/pre-push.mjs", "scripts/pre-push.test.mjs", ".husky/pre-push", ".github/workflows/release.yml", ".github/workflows/ci-preflight.yml"]) {
    assert.equal(ids([file])[0], "ci-config", file)
  }
  for (const file of ["scripts/prepare-instrument-ci.mjs", "apps/instrument-gateway/bootstrap.py", ".github/workflows/release.yml"]) {
    const plan = ids([file])
    assert.ok(plan.includes("gateway-cli"), file)
    assert.ok(plan.indexOf("gateway-cli") < plan.indexOf("lint"), file)
  }
  assert.equal(checks.gatewayCli.env.RUN_BOOTSTRAP_ATTESTATION_TESTS, "1")
  assert.ok(checks.gatewayCli.args.includes("test_bootstrap.py"))
})

test("full mode includes every local gate even for an empty or docs-only diff", () => {
  const required = ["ci-config", "version", "gateway-cli", "api-lock", "gateway-lock", "compute-lock", "lint", "types", "api-compile", "api-tests", "release-metadata", "deployment-identity", "instrument-contract", "research-integration", "gateway-tests", "interface-tests", "interface-demo", "compute-runner-tests", "compute-engine", "docs", "build", "full-e2e"]
  for (const files of [[], ["README.md"]]) {
    assert.deepEqual(new Set(ids(files, true)), new Set(required))
    assert.deepEqual(new Set(ids(files, true, "darwin")), new Set([...required, "native-build-tests"]))
  }
  const registered = new Set(Object.values(checks).map(check => check.id))
  assert.deepEqual(new Set([...ids([], true, "darwin"), "ai-e2e"]), registered)
})

test("native compilation never opts into graphical or physical equipment tests", () => {
  const plan = buildCheckPlan(["apps/instrument-interface/src/native-cli.mjs"], false, "darwin")
  const native = plan.find(check => check.id === "native-build-tests")
  assert.equal(native.env.RUN_INTERFACE_NATIVE_BUILD_TESTS, "1")
  assert.equal(native.env.RUN_INTERFACE_NATIVE_TESTS, "0")
  assert.equal(native.env.RUN_INSTRUMENT_NATIVE_JOB_TESTS, "0")
  assert.equal(plan.find(check => check.id === "research-integration").env.RUN_INSTRUMENT_NATIVE_JOB_TESTS, "0")
  assert.equal(plan.find(check => check.id === "interface-tests").env.RUN_INTERFACE_NATIVE_TESTS, "0")
  assert.ok(!ids(["apps/instrument-interface/src/native-cli.mjs"]).includes("native-build-tests"))
})

test("interface CI path filters do not silently outrun local check selection", () => {
  const workflow = load(readFileSync(".github/workflows/instrument-interface.yml", "utf8"))
  for (const event of ["push", "pull_request"]) {
    for (const pattern of workflow.on[event].paths) {
      const file = pattern.replace("**", "fixture.mjs").replace("*", "fixture")
      // Preparation/hook code is tested without invoking privileged CI setup locally.
      if (/^scripts\/(?:prepare-instrument-ci|pre-push)/.test(file))
        includes([file], ["ci-config"])
      else
        includes([file], ["gateway-cli", "instrument-contract", "interface-tests", "interface-demo", "native-build-tests"], "darwin")
    }
  }
})

test("Gateway, Compute Runner and contract changes keep their unit and integration gates", () => {
  includes(["apps/instrument-gateway/src/airalogy_instrument_gateway/runtime.py"], ["gateway-cli", "research-integration", "gateway-tests", "interface-tests"])
  includes(["apps/instrument-gateway/examples/http-reader/manifest.json"], ["research-integration", "gateway-tests"])
  includes(["apps/compute-runner/src/airalogy_compute_runner/runtime.py"], ["compute-runner-tests", "compute-engine", "research-integration"])
  includes(["scripts/compute-runner-integration.mjs"], ["compute-runner-tests", "compute-engine", "research-integration"])
  includes(["scripts/research-integration.mjs"], ["research-integration"])
  includes(["apps/api/app/services/analysis_compute_runtime.py"], ["api-tests", "research-integration", "compute-engine"])
  for (const file of ["apps/api/app/services/instrument_adapter_contract.py", "apps/api/app/services/instrument_package_contract.py", "apps/api/app/services/instrument_installation_contract.py", "apps/api/app/services/instrument_activation_contract.py", "apps/api/app/services/instrument_output_contract.py", "apps/api/app/services/instrument_authoring_contract.py"])
    includes([file], ["api-tests", "research-integration", "gateway-tests", "instrument-contract"])
  includes(["scripts/sync-instrument-contract.mjs"], ["gateway-tests", "instrument-contract", "interface-tests"])
  for (const file of ["apps/api/app/services/research_tools.py", "apps/api/app/services/persistent_jobs.py", "apps/api/app/routers/instrument_integrations.py", "apps/api/tests/activation_acceptance.py", "apps/api/tests/instrument_output_acceptance.py"])
    includes([file], ["api-tests", "research-integration"])
})

test("isolated analysis edits retain real database and worker acceptance", () => {
  const analysisFiles = [
    "apps/api/app/models/analysis.py",
    "apps/api/app/models/analysis_ai.py",
    "apps/api/app/routers/analyses.py",
    "apps/api/app/routers/analysis_ai.py",
    "apps/api/app/services/analysis_ai.py",
    "apps/api/app/services/analysis_generation.py",
    "apps/api/app/services/analysis_engine.py",
    "apps/api/app/services/analysis_schema.py",
    "apps/api/app/services/record_analyses.py",
    "apps/api/tests/test_analysis_models.py",
    "apps/api/tests/test_analysis_engine.py",
    "apps/api/tests/test_analysis_schema.py",
    "apps/api/tests/test_record_analysis_postgres.py",
    "apps/api/tests/test_record_analysis_ai_postgres.py",
    "apps/api/tests/test_analysis_ai.py",
    "apps/api/migrations/versions/0059_analysis.py",
    "apps/api/migrations/versions/0060_analysis_ai.py",
    "apps/api/migrations/versions/0062_analysis_compute_ai.py",
    "apps/api/app/services/analysis_compute_ai.py",
    "apps/api/tests/test_record_analysis_compute_ai_postgres.py",
    "apps/api/tests/test_analysis_compute_ai_runner_postgres.py",
  ]
  for (const file of analysisFiles) {
    includes([file], ["api-tests", "research-integration"])
    assert.ok(!ids([file]).includes("gateway-tests"), `${file}: unrelated Gateway tests selected`)
  }
  const workflow = load(readFileSync(".github/workflows/research-integration.yml", "utf8"))
  for (const event of ["push", "pull_request"])
    assert.ok(workflow.on[event].paths.includes("apps/api/**"), `${event}: analysis API and test edits must reach CI integration`)
  const commands = Object.values(workflow.jobs).flatMap(job => job.steps ?? []).map(step => step.run ?? "").join("\n")
  assert.ok(commands.includes("pnpm research:integration"))
  assert.deepEqual(checks.researchIntegration.args, ["pnpm", "research:integration"])
  const runner = readFileSync("tests/e2e/scripts/research-integration.sh", "utf8")
  assert.ok(runner.includes("tests/test_record_analysis_postgres.py"), "the shared integration runner must execute real analysis acceptance by default")
  assert.ok(runner.includes("tests/test_record_analysis_ai_postgres.py"), "Aira analysis edits must retain real permissions, persistence and calculation tests")
  assert.ok(runner.includes("tests/test_record_analysis_compute_postgres.py"))
  assert.ok(runner.includes("tests/test_analysis_compute_runtime_postgres.py"))
  assert.ok(runner.includes("tests/test_record_analysis_compute_ai_postgres.py"))
  assert.ok(runner.includes("tests/test_analysis_compute_ai_runner_postgres.py"))
  const entry = readFileSync("scripts/research-integration.mjs", "utf8")
  assert.ok(entry.includes("prepareComputeTestImage()"), "real execution cannot silently skip in the shared gate")
  assert.ok(entry.includes("tests/e2e/scripts/research-integration.sh"))
  assert.equal(JSON.parse(readFileSync("package.json", "utf8")).scripts["research:integration"], "node scripts/research-integration.mjs")
  for (const event of ["push", "pull_request"])
    assert.ok(workflow.on[event].paths.includes("apps/compute-runner/src/**"), "Runner-only changes must still verify the real server contract")
})

test("versioned Workflow changes retain database and runtime acceptance", () => {
  for (const file of [
    "apps/api/app/models/workflow_definition.py",
    "apps/api/app/routers/workflow_definitions.py",
    "apps/api/app/services/workflow_contracts.py",
    "apps/api/app/services/workflow_definitions.py",
    "apps/api/app/services/workflow_data.py",
    "apps/api/app/services/workflow_resolutions.py",
    "apps/api/app/services/workflow_visibility.py",
    "apps/api/app/services/workflow_analysis_methods.py",
    "apps/api/app/services/workflow_analysis_runtime.py",
    "apps/api/app/services/workflow_compute_contracts.py",
    "apps/api/app/services/workflow_compute_governance.py",
    "apps/api/app/services/workflow_compute_runtime.py",
    "apps/api/app/services/workflow_file_contracts.py",
    "apps/api/app/services/workflow_files.py",
    "apps/api/app/services/workflow_conversions.py",
    "apps/api/app/routers/workflow_conversions.py",
    "apps/api/app/models/workflow_file.py",
    "apps/api/app/models/workflow_conversion.py",
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
    "apps/api/app/models/workflow_analysis.py",
    "apps/api/tests/test_workflow_definitions_postgres.py",
    "apps/api/tests/test_workflow_binding_postgres.py",
    "apps/api/tests/test_workflow_condition_postgres.py",
    "apps/api/tests/test_workflow_visibility_postgres.py",
    "apps/api/tests/test_workflow_analysis_methods_postgres.py",
    "apps/api/tests/test_workflow_analysis_runtime_postgres.py",
    "apps/api/tests/test_workflow_analysis_lifecycle_postgres.py",
    "apps/api/tests/test_workflow_compute_methods_postgres.py",
    "apps/api/tests/test_workflow_compute_locks_postgres.py",
    "apps/api/tests/test_workflow_compute_runtime_postgres.py",
    "apps/api/tests/test_workflow_compute_r_postgres.py",
    "apps/api/tests/test_workflow_conversions_postgres.py",
    "apps/api/tests/test_workflow_file_contracts.py",
    "apps/api/tests/test_workflow_files_postgres.py",
    "apps/api/tests/test_research_asset_visibility_postgres.py",
    "apps/api/tests/test_research_context_visibility_postgres.py",
    "apps/api/app/services/research_asset_visibility.py",
    "apps/api/migrations/versions/0063_workflow_definitions.py",
    "apps/api/migrations/versions/0064_workflow_node_resolutions.py",
    "apps/api/migrations/versions/0065_workflow_analysis.py",
    "apps/api/migrations/versions/0066_workflow_compute_methods.py",
    "apps/api/migrations/versions/0067_workflow_legacy_conversions.py",
    "apps/api/migrations/versions/0068_workflow_file_bindings.py",
  ])
    includes([file], ["api-tests", "research-integration"])
  assert.ok(readFileSync("tests/e2e/scripts/research-integration.sh", "utf8").includes("tests/test_workflow_definitions_postgres.py"))
  assert.ok(readFileSync("tests/e2e/scripts/research-integration.sh", "utf8").includes("tests/test_workflow_binding_postgres.py"))
  assert.ok(readFileSync("tests/e2e/scripts/research-integration.sh", "utf8").includes("tests/test_workflow_condition_postgres.py"))
  assert.ok(readFileSync("tests/e2e/scripts/research-integration.sh", "utf8").includes("tests/test_workflow_compute_methods_postgres.py"))
  assert.ok(readFileSync("tests/e2e/scripts/research-integration.sh", "utf8").includes("tests/test_workflow_compute_locks_postgres.py"))
  assert.ok(readFileSync("tests/e2e/scripts/research-integration.sh", "utf8").includes("tests/test_workflow_compute_runtime_postgres.py"))
  assert.ok(readFileSync("tests/e2e/scripts/research-integration.sh", "utf8").includes("tests/test_workflow_compute_r_postgres.py"))
  assert.ok(readFileSync("tests/e2e/scripts/research-integration.sh", "utf8").includes("tests/test_workflow_conversions_postgres.py"))
  assert.ok(readFileSync("tests/e2e/scripts/research-integration.sh", "utf8").includes("tests/test_lab_workflow_file_cleanup_postgres.py"))
  assert.ok(readFileSync("tests/e2e/scripts/research-integration.sh", "utf8").includes("tests/test_workflow_files_postgres.py"))
  assert.ok(readFileSync("tests/e2e/scripts/research-integration.sh", "utf8").includes("tests/test_research_asset_visibility_postgres.py"))
  assert.ok(readFileSync("tests/e2e/scripts/research-integration.sh", "utf8").includes("tests/test_research_context_visibility_postgres.py"))
  assert.ok(readFileSync("tests/e2e/scripts/research-integration.sh", "utf8").includes("tests/test_workflow_visibility_postgres.py"))
  for (const file of ["methods", "runtime", "lifecycle"])
    assert.ok(readFileSync("tests/e2e/scripts/research-integration.sh", "utf8").includes(`tests/test_workflow_analysis_${file}_postgres.py`))
})

test("release identity, archive and lockfile changes have matching gates", () => {
  for (const file of ["VERSION", ".github/workflows/release.yml", "scripts/release-metadata-lib.mjs", "scripts/release-migration-head.py", "scripts/create-release-metadata.mjs", "scripts/check-release-stage.mjs", "scripts/deployment-identity.test.sh", "deploy/single-lab/.env.example", "apps/api/migrations/versions/0057_instrument_survey.py"])
    includes([file], ["release-metadata", "deployment-identity"])
  for (const [directory, check] of [["api", "api-lock"], ["instrument-gateway", "gateway-lock"], ["compute-runner", "compute-lock"]]) {
    for (const name of ["pyproject.toml", "uv.lock"])
      includes([`apps/${directory}/${name}`], [check])
  }
})

test("CI invokes shared check IDs instead of duplicating their commands", () => {
  for (const [file, required] of [
    ["instrument-interface.yml", ["version", "instrument-contract", "interface-tests", "native-build-tests", "interface-demo"]],
    ["instrument-gateway.yml", ["gateway-cli", "gateway-tests"]],
    ["ci-preflight.yml", ["ci-config", "gateway-cli"]],
    ["release.yml", ["ci-config", "gateway-cli"]],
    ["compute-runner.yml", ["compute-engine"]],
  ]) {
    const workflow = load(readFileSync(`.github/workflows/${file}`, "utf8"))
    const commands = Object.values(workflow.jobs).flatMap(job => job.steps ?? []).map(step => step.run ?? "").join("\n")
    for (const id of required)
      assert.ok(commands.split("\n").includes(`node scripts/pre-push.mjs --check ${id}`), `${file}: missing shared ${id}`)
  }
  assert.equal(readFileSync(".husky/pre-commit", "utf8").trim(), "corepack pnpm lint-staged")
  assert.equal(readFileSync(".husky/pre-push", "utf8").trim(), "node scripts/pre-push.mjs")
})

test("unknown check IDs and misspelled flags cannot silently pass", () => {
  for (const args of [["--check", "unknown"], ["--check"], ["--ful"]]) {
    const result = spawnSync(process.execPath, ["scripts/pre-push.mjs", ...args], { encoding: "utf8", timeout: 5000 })
    assert.equal(result.error, undefined)
    assert.notEqual(result.status, 0)
  }
})

test("a failing gate stops the runner and preserves its exit code", () => {
  const result = spawnSync(process.execPath, ["--input-type=module", "-e", `
    import { runCheck } from './scripts/pre-push.mjs';
    runCheck({ label: 'owned failing fixture', command: process.execPath, args: ['-e', 'process.exit(7)'] });
    console.log('MUST_NOT_RUN');
  `], { encoding: "utf8", timeout: 5000 })
  assert.equal(result.error, undefined)
  assert.equal(result.status, 7)
  assert.ok(!result.stdout.includes("MUST_NOT_RUN"))
})

test("ambient graphical opt-ins cannot escape into ordinary pre-push checks", () => {
  const flags = ["RUN_INTERFACE_NATIVE_TESTS", "RUN_INTERFACE_NATIVE_BUILD_TESTS", "RUN_INSTRUMENT_NATIVE_JOB_TESTS"]
  const result = spawnSync(process.execPath, ["--input-type=module", "-e", `
    import { runCheck } from './scripts/pre-push.mjs';
    runCheck({ label: 'owned environment fixture', command: process.execPath,
      args: ['-e', 'console.log(JSON.stringify(${JSON.stringify(flags)}.map(key => process.env[key])))'] });
  `], { encoding: "utf8", timeout: 5000, env: { ...process.env, ...Object.fromEntries(flags.map(key => [key, "1"])) } })
  assert.equal(result.error, undefined)
  assert.equal(result.status, 0, result.stderr)
  assert.deepEqual(JSON.parse(result.stdout.trim().split("\n").at(-1)), ["0", "0", "0"])
})

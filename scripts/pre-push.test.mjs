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
  const required = ["ci-config", "version", "gateway-cli", "api-lock", "gateway-lock", "compute-lock", "lint", "types", "api-compile", "api-tests", "release-metadata", "deployment-identity", "instrument-contract", "research-integration", "gateway-tests", "interface-tests", "interface-demo", "compute-runner-tests", "docs", "build", "full-e2e"]
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
  includes(["apps/compute-runner/src/airalogy_compute_runner/runtime.py"], ["compute-runner-tests"])
  for (const file of ["apps/api/app/services/instrument_adapter_contract.py", "apps/api/app/services/instrument_package_contract.py", "apps/api/app/services/instrument_installation_contract.py", "apps/api/app/services/instrument_activation_contract.py", "apps/api/app/services/instrument_output_contract.py", "apps/api/app/services/instrument_authoring_contract.py"])
    includes([file], ["api-tests", "research-integration", "gateway-tests", "instrument-contract"])
  includes(["scripts/sync-instrument-contract.mjs"], ["gateway-tests", "instrument-contract", "interface-tests"])
  for (const file of ["apps/api/app/services/research_tools.py", "apps/api/app/services/persistent_jobs.py", "apps/api/app/routers/instrument_integrations.py", "apps/api/tests/activation_acceptance.py", "apps/api/tests/instrument_output_acceptance.py"])
    includes([file], ["api-tests", "research-integration"])
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

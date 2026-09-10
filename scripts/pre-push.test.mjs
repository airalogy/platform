/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import test from "node:test"
import { buildCheckPlan } from "./pre-push.mjs"

function checkIds(files, fullRequested = false, host = "linux") {
  return buildCheckPlan(files, fullRequested, host).map(check => check.id)
}

test("documentation changes add the documentation build", () => {
  assert.deepEqual(checkIds(["docs/guide/getting-started.md"]), [
    "lint",
    "types",
    "api-compile",
    "docs",
  ])
})

test("AI capability surfaces add the focused browser test", () => {
  assert.deepEqual(checkIds(["apps/web/src/store/modules/instance/index.ts"]), [
    "lint",
    "types",
    "api-compile",
    "ai-e2e",
  ])
})

test("API changes add unit tests before focused browser coverage", () => {
  assert.deepEqual(checkIds(["apps/api/app/config.py"]), [
    "lint",
    "types",
    "api-compile",
    "api-tests",
    "ai-e2e",
  ])
})

test("Instrument Gateway changes add its isolated runtime tests", () => {
  assert.deepEqual(
    checkIds(["apps/instrument-gateway/src/airalogy_instrument_gateway/runtime.py"]),
    ["lint", "types", "api-compile", "research-integration", "gateway-tests"],
  )
  assert.deepEqual(checkIds([".github/workflows/instrument-gateway.yml"]), [
    "lint",
    "types",
    "api-compile",
    "gateway-tests",
  ])
})

test("Compute Runner changes add its isolated runtime tests", () => {
  assert.deepEqual(checkIds(["apps/compute-runner/src/airalogy_compute_runner/runtime.py"]), [
    "lint",
    "types",
    "api-compile",
    "compute-runner-tests",
  ])
  assert.deepEqual(checkIds([".github/workflows/compute-runner.yml"]), [
    "lint",
    "types",
    "api-compile",
    "compute-runner-tests",
  ])
})

test("E2E infrastructure changes run the full browser suite", () => {
  assert.deepEqual(checkIds(["tests/e2e/scripts/start-api.sh"]), [
    "lint",
    "types",
    "api-compile",
    "full-e2e",
  ])
})

test("the explicit full mode runs the full browser suite", () => {
  assert.deepEqual(checkIds(["README.md"], true), ["lint", "types", "api-compile", "release-metadata", "research-integration", "interface-tests", "full-e2e"])
})

test("native changes compile on macOS without ever opting into graphical tests", () => {
  const files = ["apps/instrument-gateway/src/airalogy_instrument_gateway/interface_process.py"]
  const plan = buildCheckPlan(files, false, "darwin")
  assert.ok(plan.some(check => check.id === "interface-tests"))
  const native = plan.find(check => check.id === "native-build-tests")
  assert.equal(native.env.RUN_INTERFACE_NATIVE_BUILD_TESTS, "1")
  assert.equal(native.env.RUN_INTERFACE_NATIVE_TESTS, "0")
  assert.equal(native.env.RUN_INSTRUMENT_NATIVE_JOB_TESTS, "0")
  assert.equal(plan.find(check => check.id === "research-integration").env.RUN_INSTRUMENT_NATIVE_JOB_TESTS, "0")
  assert.equal(plan.find(check => check.id === "interface-tests").env.RUN_INTERFACE_NATIVE_TESTS, "0")
  assert.ok(!checkIds(files, false, "linux").includes("native-build-tests"))
  assert.ok(checkIds(["README.md"], true, "darwin").includes("native-build-tests"))
})

test("interface runtime, demo and pinned browser dependencies select actual browser checks", () => {
  for (const file of [".github/workflows/instrument-interface.yml", "scripts/instrument-gui-demo.mjs"])
    assert.deepEqual(checkIds([file]), ["lint", "types", "api-compile", "interface-tests"])
  for (const file of ["apps/instrument-interface/src/browser-session.mjs", "scripts/instrument-interface-example.mjs", "scripts/instrument-interface-worker-example.mjs"])
    assert.deepEqual(checkIds([file]), ["lint", "types", "api-compile", "research-integration", "interface-tests"])
  for (const file of ["package.json", "pnpm-workspace.yaml", "pnpm-lock.yaml"])
    assert.ok(checkIds([file]).includes("interface-tests"))
})

test("migration and release changes require release metadata checks", () => {
  for (const file of ["VERSION", ".github/workflows/release.yml", "scripts/release-metadata.test.mjs", "scripts/release-metadata-lib.mjs", "deploy/single-lab/.env.example"]) {
    assert.deepEqual(checkIds([file]), ["lint", "types", "api-compile", "release-metadata"])
  }
  assert.deepEqual(checkIds(["apps/api/migrations/versions/new_revision.py"]), ["lint", "types", "api-compile", "release-metadata", "api-tests"])
  assert.deepEqual(checkIds(["apps/api/migrations/versions/0054_instrument_outputs.py"]), ["lint", "types", "api-compile", "release-metadata", "api-tests", "research-integration"])
})

test("research runtime changes require real database integration", () => {
  assert.deepEqual(checkIds(["apps/instrument-gateway/examples/http-reader/manifest.json"]), ["lint", "types", "api-compile", "research-integration", "gateway-tests"])
  assert.deepEqual(checkIds(["apps/api/tests/http_read_acceptance.py"]), ["lint", "types", "api-compile", "api-tests", "research-integration"])
  for (const file of ["apps/api/app/services/research_tools.py", "apps/api/app/services/persistent_jobs.py", "apps/api/tests/test_research_integration.py", "apps/api/app/routers/instrument_integrations.py", "apps/api/tests/activation_acceptance.py", "apps/api/tests/instrument_output_acceptance.py"]) {
    assert.deepEqual(checkIds([file]), ["lint", "types", "api-compile", "api-tests", "research-integration"])
  }
})

test("generated instrument contract changes run both API and Gateway tests", () => {
  assert.deepEqual(checkIds(["scripts/instrument-authoring-example.mjs"]), ["lint", "types", "api-compile", "gateway-tests"])
  assert.deepEqual(checkIds(["apps/api/app/services/instrument_adapter_contract.py"]), ["lint", "types", "api-compile", "api-tests", "research-integration", "gateway-tests"])
  assert.deepEqual(checkIds(["apps/api/app/services/instrument_package_contract.py"]), ["lint", "types", "api-compile", "api-tests", "research-integration", "gateway-tests"])
  assert.deepEqual(checkIds(["apps/api/app/services/instrument_installation_contract.py"]), ["lint", "types", "api-compile", "api-tests", "research-integration", "gateway-tests"])
  assert.deepEqual(checkIds(["apps/api/app/services/instrument_activation_contract.py"]), ["lint", "types", "api-compile", "api-tests", "research-integration", "gateway-tests"])
  assert.deepEqual(checkIds(["apps/api/app/services/instrument_output_contract.py"]), ["lint", "types", "api-compile", "api-tests", "research-integration", "gateway-tests"])
  assert.deepEqual(checkIds(["apps/api/app/services/instrument_authoring_contract.py"]), ["lint", "types", "api-compile", "api-tests", "research-integration", "gateway-tests"])
  assert.deepEqual(checkIds(["scripts/sync-instrument-contract.mjs"]), ["lint", "types", "api-compile", "gateway-tests"])
})

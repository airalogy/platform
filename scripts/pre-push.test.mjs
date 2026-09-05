/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import test from "node:test"
import { buildCheckPlan } from "./pre-push.mjs"

function checkIds(files, fullRequested = false) {
  return buildCheckPlan(files, fullRequested).map(check => check.id)
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
    ["lint", "types", "api-compile", "gateway-tests"],
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
  assert.deepEqual(checkIds(["README.md"], true), ["lint", "types", "api-compile", "release-metadata", "research-integration", "full-e2e"])
})

test("migration and release changes require release metadata checks", () => {
  for (const file of ["VERSION", ".github/workflows/release.yml", "scripts/release-metadata.test.mjs", "scripts/release-metadata-lib.mjs", "deploy/single-lab/.env.example"]) {
    assert.deepEqual(checkIds([file]), ["lint", "types", "api-compile", "release-metadata"])
  }
  assert.deepEqual(checkIds(["apps/api/migrations/versions/new_revision.py"]), ["lint", "types", "api-compile", "release-metadata", "api-tests"])
})

test("research runtime changes require real database integration", () => {
  for (const file of ["apps/api/app/services/research_tools.py", "apps/api/app/services/persistent_jobs.py", "apps/api/tests/test_research_integration.py"]) {
    assert.deepEqual(checkIds([file]), ["lint", "types", "api-compile", "api-tests", "research-integration"])
  }
})

/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { load } from "js-yaml"
import { requiredSourceCI, selectSourceRun, verifySourceCI, verifySourceJobs } from "./release-ci.mjs"

const context = { repository: "airalogy/platform", sha: "a".repeat(40), tag: "v0.3.0", workflowId: 1, now: Date.parse("2026-10-08T00:00:00Z") }
function success() {
  return { id: 10, run_number: 10, run_attempt: 1, workflow_id: 1, head_sha: context.sha, head_branch: "main", head_repository: { full_name: context.repository }, event: "push", status: "completed", conclusion: "success", updated_at: "2026-10-07T00:00:00Z" }
}
const job = name => ({ name, status: "completed", conclusion: "success", labels: ["ubuntu-latest"] })

test("source CI reuse requires exact SHA, repository, workflow and trusted event", () => {
  assert.equal(selectSourceRun([success()], context).id, 10)
  assert.equal(selectSourceRun([{ ...success(), event: "workflow_dispatch", head_branch: context.tag }], context).id, 10)
  for (const change of [{ head_sha: "b".repeat(40) }, { head_repository: { full_name: "other/platform" } }, { workflow_id: 2 }, { event: "pull_request" }, { head_branch: "feature" }, { event: "workflow_run" }])
    assert.throws(() => selectSourceRun([{ ...success(), ...change }], context), /No trusted/)
})

test("a failed, pending, cancelled or stale latest run cannot reuse an older success", () => {
  for (const change of [{ conclusion: "failure" }, { conclusion: "cancelled" }, { conclusion: "skipped" }, { status: "in_progress", conclusion: null }])
    assert.throws(() => selectSourceRun([success(), { ...success(), id: 11, run_number: 11, ...change }], context), /older passing/)
  for (const updated_at of ["2026-09-01", "2027-01-01", "invalid"])
    assert.throws(() => selectSourceRun([{ ...success(), updated_at }], context), /freshness/)
})

test("every required job and shard must actually pass, not be skipped or absent", () => {
  assert.doesNotThrow(() => verifySourceJobs([job("one"), job("two")], ["one", "two"]))
  for (const jobs of [[], [job("one")], [job("one"), job("one"), job("two")], [job("one"), { ...job("two"), conclusion: "skipped" }], [job("one"), { ...job("two"), labels: ["self-hosted"] }]])
    assert.throws(() => verifySourceJobs(jobs, ["one", "two"]))
})

function fixtureRequest({ failure, changedAttempt = false, paginate = false } = {}) {
  const files = Object.keys(requiredSourceCI)
  return async (path) => {
    if (failure)
      throw new Error("GitHub unavailable")
    const prefix = "/repos/airalogy/platform/actions"
    const file = path.match(/\/workflows\/(.+\.yml)$/)?.[1]
    if (file)
      return { id: files.indexOf(file) + 1, path: `.github/workflows/${file}`, state: "active" }
    const listing = path.match(/\/workflows\/(\d+)\/runs\?/)
    if (listing) {
      const id = Number(listing[1])
      return { total_count: 1, workflow_runs: [{ ...success(), id, workflow_id: id }] }
    }
    const jobs = path.match(/\/runs\/(\d+)\/attempts\/1\/jobs\?per_page=100&page=(\d+)/)
    if (jobs) {
      const selected = requiredSourceCI[files[Number(jobs[1]) - 1]].map(job)
      const page = Number(jobs[2])
      const result = paginate ? (page === 1 ? selected.slice(0, 1) : selected.slice(1)) : selected
      return { total_count: selected.length, jobs: result }
    }
    const current = path.match(new RegExp(`^${prefix}/runs/(\\d+)$`))
    if (current)
      return { ...success(), id: Number(current[1]), workflow_id: Number(current[1]), run_attempt: changedAttempt ? 2 : 1 }
    throw new Error(`Unexpected request: ${path}`)
  }
}

test("source CI verification checks all workflows, exact attempt jobs and pagination", async () => {
  const result = await verifySourceCI({ ...context, request: fixtureRequest({ paginate: true }) })
  assert.equal(result.status, "verified")
  assert.equal(result.git_sha, context.sha)
  assert.equal(result.workflows.length, 9)
  assert.equal(result.workflows.find(item => item.workflow === "e2e.yml").jobs.length, 7)
  await assert.rejects(verifySourceCI({ ...context, request: fixtureRequest({ failure: true }) }), /unavailable/)
  await assert.rejects(verifySourceCI({ ...context, request: fixtureRequest({ changedAttempt: true }) }), /changed during/)
  await assert.rejects(verifySourceCI({ ...context, sha: "HEAD", request: fixtureRequest() }), /full commit/)
})

test("incomplete or ambiguous GitHub inventories never qualify a release", async () => {
  for (const replacement of [{}, { total_count: 101 }, { total_count: 0 }, { total_count: 2 }]) {
    const base = fixtureRequest()
    const request = async (path) => {
      const data = await base(path)
      if (path.includes("/runs?"))
        return { workflow_runs: data.workflow_runs, ...replacement }
      return data
    }
    await assert.rejects(verifySourceCI({ ...context, request }), /Incomplete source-run/)
  }
  const base = fixtureRequest()
  await assert.rejects(verifySourceCI({ ...context, request: async (path) => {
    const data = await base(path)
    return path.includes("/jobs?") ? { total_count: 2, jobs: [] } : data
  } }), /Incomplete source-job/)
})

test("release requires trusted source evidence before builds but retains immutable artifact acceptance", () => {
  const release = load(readFileSync(".github/workflows/release.yml", "utf8"))
  const steps = release.jobs.verify.steps
  const index = steps.findIndex(step => step.run?.startsWith("node scripts/release-ci.mjs"))
  assert.ok(index >= 0 && index < steps.findIndex(step => step.run === "pnpm install --frozen-lockfile"))
  assert.equal(release.permissions.actions, "read")
  assert.ok(!steps.some(step => ["pnpm build", "pnpm lint", "pnpm type-check", "pnpm api:test"].includes(step.run)))
  assert.ok(release.jobs.release.steps.some(step => step.name === "Smoke test the exact released component set"))
  assert.ok(release.jobs.release.steps.some(step => step.name === "Verify public installation access"))
  const source = readFileSync("deploy/single-lab/web.Dockerfile", "utf8")
  assert.match(source, /FROM --platform=\$BUILDPLATFORM node:22-bookworm-slim AS builder/)
  assert.match(source, /FROM caddy:2\.10\.2-alpine/)
  for (const file of Object.keys(requiredSourceCI)) {
    const workflow = load(readFileSync(`.github/workflows/${file}`, "utf8"))
    assert.ok(Object.hasOwn(workflow.on, "workflow_dispatch"), `${file}: allow exact-tag evidence refresh`)
  }
  const frontend = load(readFileSync(".github/workflows/frontend-lint.yml", "utf8"))
  assert.ok(frontend.jobs.lint.steps.some(step => step.run === "pnpm type-check"), "release reuse must retain the entire workspace type/test scope")
})

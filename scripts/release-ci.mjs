import { execFileSync } from "node:child_process"
import { createHash } from "node:crypto"
import { readFileSync, writeFileSync } from "node:fs"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { parseArgs } from "node:util"

// A release version change reaches every one of these workflows. Missing runs
// are not successes: dispatch the missing workflow at the same immutable tag.
export const requiredSourceCI = {
  "ci-preflight.yml": ["check (ubuntu-latest)", "check (macos-latest)"],
  "backend-smoke.yml": ["smoke"],
  "frontend-lint.yml": ["lint"],
  "docs.yml": ["build"],
  "research-integration.yml": ["postgres-runtime"],
  "instrument-gateway.yml": ["test-and-package"],
  "instrument-interface.yml": ["synthetic-browser (ubuntu-latest)", "synthetic-browser (macos-latest)"],
  "compute-runner.yml": ["test-and-package"],
  "e2e.yml": ["preflight", ...[1, 2, 3, 4].map(index => `chromium-enabled-${index}-of-4`), "chromium-disabled-1-of-1", "browser-gate"],
}

export function selectSourceRun(runs, { repository, sha, tag, workflowId, now }) {
  const trusted = runs.filter(run => run.head_sha === sha && run.workflow_id === workflowId
    && run.head_repository?.full_name === repository
    && ((run.event === "push" && run.head_branch === "main")
      || (run.event === "workflow_dispatch" && ["main", tag].includes(run.head_branch))))
  const latest = trusted.sort((a, b) => b.run_number - a.run_number || b.run_attempt - a.run_attempt)[0]
  if (!latest)
    throw new Error("No trusted source CI run for this exact commit; dispatch the workflow at the release tag")
  if (latest.status !== "completed" || latest.conclusion !== "success")
    throw new Error(`Latest source CI run ${latest.id} is ${latest.status}/${latest.conclusion}; an older passing attempt cannot replace it`)
  const updated = Date.parse(latest.updated_at)
  if (!Number.isFinite(updated) || updated > now || now - updated > 7 * 86400_000)
    throw new Error("Source CI evidence is outside the seven-day release freshness window")
  return latest
}

export function verifySourceJobs(jobs, expected) {
  for (const name of expected) {
    const found = jobs.filter(job => job.name === name)
    if (found.length !== 1 || found[0].status !== "completed" || found[0].conclusion !== "success")
      throw new Error(`Required source CI job did not pass: ${name}`)
  }
  if (jobs.some(job => job.status !== "completed" || job.conclusion !== "success" || job.labels?.includes("self-hosted")))
    throw new Error("Source CI contains skipped, failed, incomplete or self-hosted jobs")
}

export async function verifySourceCI({ repository, sha, tag, request, now = Date.now() }) {
  if (!/^[\w.-]+\/[\w.-]+$/.test(repository) || !/^[0-9a-f]{40}$/.test(sha) || !/^v\d+\.\d+\.\d+$/.test(tag))
    throw new Error("Expected a repository, full commit SHA and release tag")
  const prefix = `/repos/${repository}/actions`
  const receipts = await Promise.all(Object.entries(requiredSourceCI).map(async ([file, names]) => {
    try {
      const workflow = await request(`${prefix}/workflows/${file}`)
      if (workflow.path !== `.github/workflows/${file}` || workflow.state !== "active")
        throw new Error("Unexpected or disabled source workflow")
      const data = await request(`${prefix}/workflows/${workflow.id}/runs?head_sha=${sha}&per_page=100`)
      if (!Array.isArray(data.workflow_runs) || !Number.isInteger(data.total_count)
        || data.total_count > 100 || data.workflow_runs.length !== data.total_count) {
        throw new Error("Incomplete source-run inventory; refusing ambiguous evidence")
      }
      const run = selectSourceRun(data.workflow_runs, { repository, sha, tag, workflowId: workflow.id, now })
      const jobs = []
      for (let page = 1; ; page++) {
        const data = await request(`${prefix}/runs/${run.id}/attempts/${run.run_attempt}/jobs?per_page=100&page=${page}`)
        if (!Array.isArray(data.jobs) || !Number.isInteger(data.total_count) || page > 10)
          throw new Error("Invalid source-job inventory")
        jobs.push(...data.jobs)
        if (jobs.length === data.total_count)
          break
        if (!data.jobs.length || jobs.length > data.total_count)
          throw new Error("Incomplete source-job inventory")
      }
      verifySourceJobs(jobs, names)
      const current = await request(`${prefix}/runs/${run.id}`)
      if (current.run_attempt !== run.run_attempt || current.head_sha !== sha
        || current.workflow_id !== workflow.id || current.status !== "completed" || current.conclusion !== "success") {
        throw new Error("Source CI changed during verification")
      }
      return { workflow: file, run_id: run.id, run_attempt: run.run_attempt, jobs: jobs.map(job => job.name) }
    }
    catch (error) {
      throw new Error(`${file}: ${error.message}`, { cause: error })
    }
  }))
  return { status: "verified", repository, git_sha: sha, release_tag: tag, verified_at: new Date(now).toISOString(), workflows: receipts }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { values } = parseArgs({ options: { repository: { type: "string" }, sha: { type: "string" }, tag: { type: "string" }, output: { type: "string" } } })
  const repository = values.repository || process.env.GITHUB_REPOSITORY
  const sha = values.sha || process.env.GITHUB_SHA
  const tag = values.tag || process.env.GITHUB_REF_NAME
  if (!process.env.GH_TOKEN)
    throw new Error("GH_TOKEN with read-only Actions access is required")
  if (execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim() !== sha)
    throw new Error("Checkout and source CI commit must match exactly")
  if (execFileSync("git", ["status", "--porcelain", "--untracked-files=no"], { encoding: "utf8" }).trim())
    throw new Error("Source CI reuse requires a clean tracked checkout")
  const receipt = await verifySourceCI({ repository, sha, tag, request: async (path) => {
    const response = await fetch(`https://api.github.com${path}`, {
      headers: { "Authorization": `Bearer ${process.env.GH_TOKEN}`, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" },
      signal: AbortSignal.timeout(20_000),
    })
    if (!response.ok)
      throw new Error(`GitHub Actions evidence unavailable (HTTP ${response.status}); publication remains blocked`)
    return response.json()
  } })
  receipt.workflow_sha256 = Object.fromEntries(Object.keys(requiredSourceCI).map(file => [file, createHash("sha256").update(readFileSync(`.github/workflows/${file}`)).digest("hex")]))
  if (values.output)
    writeFileSync(values.output, `${JSON.stringify(receipt, null, 2)}\n`, { flag: "wx" })
  console.log(`Verified ${receipt.workflows.length} exact-commit source CI workflows for ${sha}`)
}

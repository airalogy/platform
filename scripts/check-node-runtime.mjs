import { readdirSync, readFileSync } from "node:fs"
import { createRequire } from "node:module"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"

const root = fileURLToPath(new URL("../", import.meta.url))

export function assertNodeRuntime(version, major) {
  const [actual, minor] = version.replace(/^v/, "").split(".").map(Number)
  if (major !== "22" || actual !== 22 || !Number.isInteger(minor) || minor < 12)
    throw new Error(`Node ${version} is unsupported. Use Node 22.12+ within 22.x, as defined in .node-version and package.json.`)
}

export function assertNodeConfiguration({ major, engines, workflows, dockerfile }) {
  // Python-only gates need the runtime guard before frontend dependencies exist.
  // YAML is needed only by the dedicated CI configuration check.
  const { load } = createRequire(import.meta.url)("js-yaml")
  if (major !== "22" || engines !== ">=22.12.0 <23")
    throw new Error("Keep .node-version and package.json engines aligned with the supported Node 22.12+ (22.x) runtime")
  for (const [name, source] of Object.entries(workflows)) {
    const workflow = load(source)
    let usesNode = false
    for (const job of Object.values(workflow.jobs ?? {})) {
      for (const step of job.steps ?? []) {
        if (!step.uses?.startsWith("actions/setup-node@"))
          continue
        usesNode = true
        if (step.with?.["node-version-file"] !== ".node-version" || step.with?.["node-version"] !== undefined)
          throw new Error(`${name}: actions/setup-node must read .node-version without a node-version override`)
      }
    }
    if (usesNode) {
      for (const event of ["push", "pull_request"]) {
        const paths = workflow.on?.[event]?.paths
        if (paths && !paths.includes(".node-version"))
          throw new Error(`${name}: filtered ${event} checks must include .node-version`)
      }
    }
  }
  if (!new RegExp(`^FROM node:${major}-bookworm-slim AS builder$`, "m").test(dockerfile))
    throw new Error("The production web builder must use the Node major from .node-version")
}

export function checkNodeRuntime() {
  const read = path => readFileSync(resolve(root, path), "utf8")
  const major = read(".node-version").trim()
  assertNodeRuntime(process.versions.node, major)
  if (JSON.parse(read("package.json")).engines?.node !== ">=22.12.0 <23")
    throw new Error("Keep package.json engines aligned with .node-version")
}

export function checkNodeConfiguration() {
  const read = path => readFileSync(resolve(root, path), "utf8")
  assertNodeConfiguration({
    major: read(".node-version").trim(),
    engines: JSON.parse(read("package.json")).engines?.node,
    workflows: Object.fromEntries(readdirSync(resolve(root, ".github/workflows"))
      .filter(name => /\.ya?ml$/.test(name)).map(name => [name, read(`.github/workflows/${name}`)])),
    dockerfile: read("deploy/single-lab/web.Dockerfile"),
  })
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  checkNodeRuntime()
  checkNodeConfiguration()
  console.log("Node runtime, CI and production builder configuration are aligned")
}

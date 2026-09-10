#!/usr/bin/env node
import { parseArgs } from "node:util"
import { canonical } from "./contract.mjs"
import { readPrivateSelection } from "./evidence.mjs"
import { prepareExploration, runExploration, syncExploration } from "./exploration.mjs"

async function main() {
  const { values, positionals } = parseArgs({ allowPositionals: true, options: Object.fromEntries(["definition", "policy", "workspace", "platform-url", "gateway-id", "resource-id", "max-iterations", "duration-seconds", "confirm"].map(key => [key, { type: "string" }])) })
  let result
  if (positionals[0] === "prepare" && positionals.length === 1) {
    const definition = JSON.parse(await readPrivateSelection(values.definition))
    const policy = JSON.parse(await readPrivateSelection(values.policy))
    result = await prepareExploration({ definition, policy, workspace: values.workspace, platformUrl: values["platform-url"], gatewayId: values["gateway-id"], resourceId: values["resource-id"], maxIterations: Number(values["max-iterations"] ?? 5), durationSeconds: Number(values["duration-seconds"] ?? 600) })
  }
  else if (positionals.length === 2 && ["run", "sync"].includes(positionals[0])) {
    result = positionals[0] === "run" ? await runExploration(positionals[1], { confirmation: values.confirm }) : await syncExploration(positionals[1])
    if (positionals[0] === "sync")
      result = { synced_reports: result.synced_reports, state: result.session.effective_state, browser_opened: false, native_actions_executed: false }
  }
  else {
    throw new Error("Use prepare with explicit definition/policy/workspace/platform/scope, run REQUEST --confirm LOCAL_PREVIEW_DIGEST, or sync REQUEST")
  }
  process.stdout.write(`${canonical(result)}\n`)
}
main().catch(() => {
  process.stderr.write("Interface development stopped. Retain private evidence; verify permissions, inputs and saved state. Do not relaunch an uncertain session.\n")
  process.exitCode = 1
})

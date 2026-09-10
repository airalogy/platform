#!/usr/bin/env node
import { parseArgs } from "node:util"
import { canonical } from "./contract.mjs"
import { readPrivateSelection } from "./evidence.mjs"
import { exportWorkflow, previewWorkflow, previewWorkflowExport, runWorkflow } from "./workflow.mjs"

async function main() {
  const { values, positionals } = parseArgs({ allowPositionals: true, options: { ...Object.fromEntries(["evidence", "workspace", "workflow", "confirm"].map(key => [key, { type: "string" }])), "ack-new-run": { type: "boolean" } } })
  if (positionals.length !== 1)
    throw new Error("Select one workflow operation")
  const operation = positionals[0]
  const required = { prepare: ["evidence"], export: ["evidence", "workspace", "confirm"], preview: ["workflow"], run: ["workflow", "evidence", "confirm", "ack-new-run"] }[operation]
  if (!required || required.some(key => !values[key]) || Object.keys(values).some(key => !required.includes(key)))
    throw new Error("Select the exact arguments for prepare, export, preview or run")
  let result
  if (operation === "prepare") {
    result = await previewWorkflowExport(values.evidence)
  }
  else if (operation === "export") {
    result = await exportWorkflow(values.evidence, { confirmation: values.confirm, workspace: values.workspace })
  }
  else {
    const workflow = JSON.parse(await readPrivateSelection(values.workflow, 524288))
    result = operation === "preview" ? await previewWorkflow(workflow) : await runWorkflow(workflow, { confirmation: values.confirm, evidenceRoot: values.evidence, acknowledgeNewRun: values["ack-new-run"] })
  }
  process.stderr.write("PRIVATE development workflow. No hardware qualification, automatic retry or physical safe-stop claim.\n")
  process.stdout.write(`${canonical(result)}\n`)
}

main().catch(() => {
  process.stderr.write("Workflow operation refused. Retain private evidence and review inputs/state; do not replay uncertain actions.\n")
  process.exitCode = 1
})

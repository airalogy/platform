#!/usr/bin/env node
import { parseArgs } from "node:util"
import { canonical } from "./contract.mjs"
import { prepareNativeReadRuntime, previewNativeReadRuntime } from "./native-read-worker-runtime.mjs"
import { prepareWorkerRuntime, previewWorkerRuntime } from "./worker-runtime.mjs"

async function main() {
  const { values, positionals } = parseArgs({ allowPositionals: true, options: Object.fromEntries(["workflow", "native-read-definition", "evidence", "workspace", "confirm"].map(key => [key, { type: "string" }])) })
  if (positionals.length !== 1 || Boolean(values.workflow) === Boolean(values["native-read-definition"]) || !values.evidence)
    throw new Error("Select exactly one workflow or native read definition, and private evidence")
  const nativeRead = Boolean(values["native-read-definition"])
  const selection = nativeRead ? values["native-read-definition"] : values.workflow
  let result
  if (positionals[0] === "preview" && !values.workspace && !values.confirm)
    result = await (nativeRead ? previewNativeReadRuntime : previewWorkerRuntime)(selection, values.evidence)
  else if (positionals[0] === "prepare" && values.workspace && values.confirm)
    result = await (nativeRead ? prepareNativeReadRuntime : prepareWorkerRuntime)(selection, { evidenceRoot: values.evidence, workspace: values.workspace, confirmation: values.confirm })
  else throw new Error("Use preview or independently confirmed prepare")
  process.stdout.write(`${canonical(result)}\n`)
}
main().catch(() => {
  process.stderr.write("Worker preparation refused. Check the explicitly selected runtime, private paths and current review digest. No application was opened.\n")
  process.exitCode = 1
})

#!/usr/bin/env node
import { parseArgs } from "node:util"
import { canonical } from "./contract.mjs"
import { readPrivateSelection } from "./evidence.mjs"
import { previewNativeRead, runNativeRead, selectNative } from "./native-survey.mjs"
import { buildNative, nativeCall } from "./native-transport.mjs"
import { prepareSurvey } from "./survey-workspace.mjs"

async function main() {
  const keys = ["workspace", "build", "bundle", "pid", "title", "locale", "redact", "definition", "confirm", "evidence"]
  const { values, positionals } = parseArgs({ allowPositionals: true, options: { ...Object.fromEntries(keys.map(key => [key, { type: "string" }])), "capture-values": { type: "boolean" }, "ack-new-read": { type: "boolean" } } })
  if (positionals.length !== 1)
    throw new Error("Select exactly one native command")
  const command = positionals[0]
  const allowed = { build: ["workspace"], doctor: ["build"], prepare: ["workspace", "build", "bundle", "pid", "title", "locale", "redact", "capture-values"], preview: ["definition"], read: ["definition", "confirm", "evidence", "ack-new-read"] }[command]
  if (!allowed || Object.keys(values).some(key => !allowed.includes(key)))
    throw new Error("Unexpected native command option")
  let result
  if (command === "build") {
    result = await buildNative(values.workspace)
  }
  else if (command === "doctor") {
    result = await nativeCall(values.build, { operation: "doctor" })
  }
  else if (command === "prepare") {
    if (!/^\d+$/.test(values.pid || ""))
      throw new Error("Select a running application PID")
    const selection = await selectNative({ buildFile: values.build, bundlePath: values.bundle, pid: Number(values.pid), title: values.title, locale: values.locale, captureValues: values["capture-values"] || false, redactIdentifiers: values.redact ? JSON.parse(await readPrivateSelection(values.redact)) : [] })
    result = await prepareSurvey(selection, values.workspace)
  }
  else {
    const definition = JSON.parse(await readPrivateSelection(values.definition))
    if (command === "preview") {
      result = await previewNativeRead(definition)
    }
    else {
      if (!values["ack-new-read"])
        throw new Error("A new read is not uncertain-run recovery")
      result = await runNativeRead(definition, { confirmation: values.confirm, evidenceRoot: values.evidence })
    }
  }
  process.stdout.write(`${canonical(result)}\n`)
}
main().catch(() => {
  // Transport failures contain only fixed codes; do not expose app/OS error bodies.
  process.stderr.write("Native operation refused. Check the selected build, process, single window and capture policy. Review private evidence and retain uncertain-run markers; no software or equipment action was authorized.\n")
  process.exitCode = 1
})

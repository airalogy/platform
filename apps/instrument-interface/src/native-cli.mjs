#!/usr/bin/env node
import { parseArgs } from "node:util"
import { canonical, digest } from "./contract.mjs"
import { readPrivateSelection } from "./evidence.mjs"
import { nativeDiscoveryResult, prepareNativeDiscovery, runNativeDiscovery } from "./native-discovery.mjs"
import { nativeLaunchStatus, prepareNativeLaunch, runNativeLaunch } from "./native-launch.mjs"
import { NativeInterfaceSession, previewNativeInterface } from "./native-session.mjs"
import { previewNativeRead, runNativeRead, selectNative } from "./native-survey.mjs"
import { prepareNativeSimulation } from "./native-template.mjs"
import { buildNative, nativeCall, nativeFailureCode } from "./native-transport.mjs"
import { prepareSurvey } from "./survey-workspace.mjs"

let selectedCommand = null

async function main() {
  const keys = ["workspace", "build", "bundle", "pid", "title", "locale", "redact", "definition", "plan", "confirm", "evidence", "request", "reason", "duration-seconds", "directory", "depth"]
  const { values, positionals } = parseArgs({ allowPositionals: true, options: { ...Object.fromEntries(keys.map(key => [key, { type: "string" }])), "capture-values": { type: "boolean" }, "ack-new-read": { type: "boolean" }, "ack-new-run": { type: "boolean" }, "ack-initialization": { type: "boolean" } } })
  if (positionals.length !== 1)
    throw new Error("Select exactly one native command")
  const command = positionals[0]
  selectedCommand = command
  const allowed = { "build": ["workspace"], "doctor": ["build"], "inspect": ["build", "bundle"], "windows": ["build", "bundle", "pid"], "prepare": ["workspace", "build", "bundle", "pid", "title", "locale", "redact", "capture-values"], "simulation-template": ["workspace", "build", "pid"], "preview": ["definition", "plan"], "read": ["definition", "confirm", "evidence", "ack-new-read"], "run": ["definition", "plan", "confirm", "evidence", "ack-new-run"], "prepare-launch": ["workspace", "build", "bundle", "reason", "duration-seconds"], "launch": ["request", "confirm", "ack-initialization"], "launch-status": ["request"], "prepare-discovery": ["directory", "depth", "workspace"], "discover": ["request", "confirm"], "discovery-result": ["request"] }[command]
  if (!allowed || Object.keys(values).some(key => !allowed.includes(key)))
    throw new Error("Unexpected native command option")
  let result
  if (command === "prepare-discovery") {
    result = await prepareNativeDiscovery({ directory: values.directory, depth: Number(values.depth ?? 0), workspace: values.workspace })
  }
  else if (command === "discover") {
    result = await runNativeDiscovery(values.request, values.confirm)
  }
  else if (command === "discovery-result") {
    result = await nativeDiscoveryResult(values.request)
  }
  else if (command === "build") {
    result = await buildNative(values.workspace)
  }
  else if (command === "doctor") {
    result = await nativeCall(values.build, { operation: "doctor" })
  }
  else if (command === "inspect") {
    result = await nativeCall(values.build, { operation: "inspect_application", bundle_path: values.bundle })
  }
  else if (command === "windows") {
    if (!/^\d+$/.test(values.pid || ""))
      throw new Error("Select the exact running application")
    const pin = await nativeCall(values.build, { operation: "pin_process", bundle_path: values.bundle, pid: Number(values.pid) })
    result = await nativeCall(values.build, { operation: "inspect_windows", pin })
  }
  else if (command === "prepare-launch") {
    result = await prepareNativeLaunch({ buildFile: values.build, bundlePath: values.bundle, workspace: values.workspace, reason: values.reason, durationSeconds: Number(values["duration-seconds"] ?? 300) })
  }
  else if (command === "launch") {
    result = await runNativeLaunch(values.request, { confirmation: values.confirm, acknowledgeInitialization: values["ack-initialization"] || false })
  }
  else if (command === "launch-status") {
    result = await nativeLaunchStatus(values.request)
  }
  else if (command === "simulation-template") {
    if (!/^\d+$/.test(values.pid || ""))
      throw new Error("Select the already running owned simulator")
    result = await prepareNativeSimulation({ buildFile: values.build, pid: Number(values.pid), workspace: values.workspace })
  }
  else if (command === "prepare") {
    if (!/^\d+$/.test(values.pid || ""))
      throw new Error("Select a running application PID")
    const selection = await selectNative({ buildFile: values.build, bundlePath: values.bundle, pid: Number(values.pid), title: values.title, locale: values.locale, captureValues: values["capture-values"] || false, redactIdentifiers: values.redact ? JSON.parse(await readPrivateSelection(values.redact)) : [] })
    result = await prepareSurvey(selection, values.workspace)
  }
  else {
    const definition = JSON.parse(await readPrivateSelection(values.definition))
    const plan = values.plan ? JSON.parse(await readPrivateSelection(values.plan)) : { schema: "airalogy.interface-plan.v1", steps: [] }
    if (command === "preview") {
      if (definition.schema === "airalogy.native-read-definition.v1") {
        if (values.plan)
          throw new Error("Read-only survey definitions cannot receive action plans")
        result = await previewNativeRead(definition)
      }
      else { result = await previewNativeInterface(definition, plan) }
    }
    else if (command === "run") {
      if (!values["ack-new-run"])
        throw new Error("A new simulation is not uncertain-run recovery")
      const session = await NativeInterfaceSession.open({ definition, plan, confirmation: values.confirm, evidenceRoot: values.evidence })
      try {
        for (let index = 0; index < plan.steps.length; index++)
          await session.step(digest(session.lastObservation))
        result = { evidence: session.evidence.directory, completed_steps: session.cursor, values: session.lastObservation.values, hardware_qualified: false }
      }
      finally { await session.close() }
    }
    else {
      if (!values["ack-new-read"])
        throw new Error("A new read is not uncertain-run recovery")
      result = await runNativeRead(definition, { confirmation: values.confirm, evidenceRoot: values.evidence })
    }
  }
  process.stdout.write(`${canonical(result)}\n`)
}
main().catch((error) => {
  if (["prepare-discovery", "discover", "discovery-result"].includes(selectedCommand)) {
    process.stderr.write("Application discovery stopped. Check the explicit canonical directory, private evidence directory, unexpired preview and exact confirmation. Discovery evidence must be outside the selected scope. Inspect a retained discovery-result offline; a request already started cannot rescan. Prepare a fresh scope for a new metadata snapshot. No application was launched or qualified.\n")
    process.exitCode = 1
    return
  }
  // Transport failures contain only fixed codes; do not expose app/OS error bodies.
  process.stderr.write(`Native operation stopped (${nativeFailureCode(error)}). Check the reviewed build, application/process, window and policy; use doctor for session/permission diagnostics. Retain private evidence: an attempted application launch or simulation write may be uncertain and must not be retried automatically. No hardware qualification or physical safe-stop is claimed.\n`)
  process.exitCode = 1
})

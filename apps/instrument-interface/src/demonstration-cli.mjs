#!/usr/bin/env node
import { createInterface } from "node:readline/promises"
import { parseArgs } from "node:util"
import { canonical } from "./contract.mjs"
import { BrowserDemonstrationSession, previewDemonstration } from "./demonstration.mjs"
import { readPrivateSelection } from "./evidence.mjs"

async function main() {
  const { values, positionals } = parseArgs({ allowPositionals: true, options: {
    "definition": { type: "string" },
    "policy": { type: "string" },
    "confirm": { type: "string" },
    "evidence": { type: "string" },
    "ack-visible-owned-simulation": { type: "boolean" },
  } })
  if (positionals.length !== 1 || !["preview", "record"].includes(positionals[0]))
    throw new Error("Use preview or record with an exact definition and policy")
  const definition = JSON.parse(await readPrivateSelection(values.definition))
  const policy = JSON.parse(await readPrivateSelection(values.policy))
  if (positionals[0] === "preview") {
    if (values.confirm || values.evidence || values["ack-visible-owned-simulation"])
      throw new Error("Preview takes definition and policy only")
    process.stdout.write(`${canonical(await previewDemonstration(definition, policy))}\n`)
    process.stderr.write("PRIVATE preview. Recording opens a visible owned HTML browser. Review code, selected controls/literal actions, initial state, privacy and success checks. No vendor/hardware authority.\n")
    return
  }
  if (!process.stdin.isTTY || !values["ack-visible-owned-simulation"])
    throw new Error("Recording requires an interactive terminal and explicit visible owned-simulation acknowledgement")
  const session = await BrowserDemonstrationSession.open({ definition, policy, confirmation: values.confirm, evidenceRoot: values.evidence, acknowledgeOwnedSimulation: true, visible: true })
  const terminal = createInterface({ input: process.stdin, output: process.stderr })
  const controller = new AbortController()
  terminal.once("close", () => controller.abort())
  let displayed = 0
  const timer = setInterval(() => {
    if (session.cursor > displayed) {
      displayed = session.cursor
      process.stderr.write(`Recorded ${displayed} operation(s). / 已记录 ${displayed} 步。\n`)
    }
    if (session.closed || session.fault)
      controller.abort()
  }, 200)
  const cancelled = () => controller.abort()
  terminal.once("SIGINT", cancelled)
  process.once("SIGTERM", cancelled)
  process.once("SIGINT", cancelled)
  try {
    process.stderr.write("Record only reviewed actions in the opened simulator. Commit a field with Tab and wait for 'Recorded' before the next operation. Input while a receipt is pending is ignored, not queued. Type finish here after the original success checks are met; any other input/EOF cancels. / 仅在模拟器示范已审核操作；输入后按 Tab，等待记录完成再进行下一步，结束后在此输入 finish。\n")
    const answer = await terminal.question("> ", { signal: controller.signal })
    if (answer !== "finish")
      throw new Error("Demonstration cancelled")
    process.stdout.write(`${canonical(await session.finish())}\n`)
  }
  finally {
    clearInterval(timer)
    terminal.close()
    process.removeListener("SIGTERM", cancelled)
    process.removeListener("SIGINT", cancelled)
    if (!session.closed)
      await session.fail("Demonstration cancelled or terminal closed; not a physical stop")
  }
}

main().catch(() => {
  process.stderr.write("Demonstration stopped. Check the exact private definition/policy, current confirmation and original evidence. A person may already have acted; no automatic replay, broad desktop access or physical stop is provided.\n")
  process.exitCode = 1
})

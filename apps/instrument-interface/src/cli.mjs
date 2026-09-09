#!/usr/bin/env node
import { parseArgs } from "node:util"
import { BrowserInterfaceSession, previewInterface } from "./browser-session.mjs"
import { canonical, digest } from "./contract.mjs"
import { readPrivateSelection } from "./evidence.mjs"

async function main() {
  const { values, positionals } = parseArgs({
    allowPositionals: true,
    options: { "definition": { type: "string" }, "plan": { type: "string" }, "confirm": { type: "string" }, "evidence": { type: "string" }, "ack-new-run": { type: "boolean" } },
  })
  if (positionals.length !== 1 || !["preview", "run"].includes(positionals[0]) || !values.definition) {
    throw new Error("Usage: airalogy-instrument-interface preview|run --definition /absolute/definition.json [--plan /absolute/plan.json]; run also requires --confirm SHA256 --evidence /private/directory --ack-new-run")
  }
  const definition = JSON.parse(await readPrivateSelection(values.definition))
  const plan = values.plan ? JSON.parse(await readPrivateSelection(values.plan)) : { schema: "airalogy.interface-plan.v1", steps: [] }
  const preview = await previewInterface(definition, plan)
  if (positionals[0] === "preview") {
    process.stdout.write(`${canonical(preview)}\n`)
    process.stderr.write("PRIVATE preview. Opening an application or GET request can affect equipment. Review target, code, network, privacy and each step. This is not a hardware authorization or safe-stop service.\n")
    return
  }
  if (!values.confirm || !values.evidence || !values["ack-new-run"])
    throw new Error("A new run requires explicit preview confirmation, private evidence location and acknowledgement; it never resumes or retries a prior physical action")
  const session = await BrowserInterfaceSession.open({ definition, plan, confirmation: values.confirm, evidenceRoot: values.evidence })
  process.stdout.write(`${canonical({ evidence: session.evidence.directory, session_id: session.sessionId })}\n`)
  try {
    for (let i = 0; i < plan.steps.length; i++) {
      await session.step(digest(session.lastObservation))
    }
  }
  finally {
    await session.close()
  }
}

main().catch((error) => {
  // Never serialize Playwright errors, page content or environment into terminal logs.
  process.stderr.write(`${error instanceof SyntaxError ? "Invalid selected JSON" : error.message}\n`)
  process.exitCode = 1
})

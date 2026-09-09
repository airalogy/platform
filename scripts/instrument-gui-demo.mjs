// Only this bundled synthetic fixture is automatically approved by the demo command.
// The generic CLI requires review and confirmation; no target arguments are accepted here.
import { spawnSync } from "node:child_process"
import { mkdtemp } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { fileURLToPath } from "node:url"
import { BrowserInterfaceSession, previewInterface } from "../apps/instrument-interface/src/browser-session.mjs"
import { digest } from "../apps/instrument-interface/src/contract.mjs"
import { createExample } from "./instrument-interface-example.mjs"

if (process.argv.length > 2)
  throw new Error("The synthetic demo accepts no application targets or browser overrides")
const root = new URL("../", import.meta.url)
const { definition, plan } = await createExample()
const preview = await previewInterface(definition, plan)
const evidenceRoot = await mkdtemp(join(tmpdir(), "airalogy-gui-demo-"))
const session = await BrowserInterfaceSession.open({ definition, plan, confirmation: preview.sha256, evidenceRoot })
const target = { application: definition.target.application, version: definition.target.version, os: "simulation", locale: definition.target.locale }
try {
  const steps = [
    { operation: "set_value", control_id: "sample.count", value: 2, before: "ready", after: "ready" },
    { operation: "invoke", control_id: "measurement.start", before: "ready", after: "completed" },
    { operation: "read", control_id: "result.value", output_key: "value", before: "completed", after: "completed" },
  ]
  const observation = () => ({
    target,
    window_id: session.sessionId,
    state: session.lastObservation.state,
    session: "interactive",
    control_owner: "gateway",
    blocking_dialog: false,
    controls: Object.entries(session.lastObservation.values).map(([id, value]) => ({ id, value: ["sample.count", "result.value"].includes(id) ? Number(value) : value, enabled: session.lastObservation.enabled[id] })),
  })
  const observations = []
  for (let i = 0; i < steps.length; i++) {
    observations.push(observation())
    await session.step(digest(session.lastObservation))
    observations.push(observation())
  }
  const bundle = {
    package: {
      schema: "airalogy.gui-rehearsal.v1",
      id: "example.browser-reader",
      version: "v1",
      target,
      source: { kind: "demonstration", reference: "Bundled synthetic browser demonstration" },
      limitations: ["Only the bundled synthetic application was exercised. No OS desktop or hardware qualification. The gateway ownership label is synthetic."],
      commands: [{ key: "measure.synthetic", version: "v1", name: "Synthetic measurement", steps }],
    },
    scenarios: [{ name: "Two synthetic samples", command_key: "measure.synthetic", command_version: "v1", window_id: session.sessionId, observations, expected_output: { value: 0.84 } }],
  }
  const verify = spawnSync("python3", ["-c", "import json,sys; from airalogy_instrument_gateway.integration_contract import rehearse; b=json.load(sys.stdin); r=rehearse(b['package'],b['scenarios']); assert r['passed'],r"], {
    cwd: fileURLToPath(root),
    env: { ...process.env, PYTHONPATH: fileURLToPath(new URL("apps/instrument-gateway/src", root)) },
    input: JSON.stringify(bundle),
    encoding: "utf8",
    timeout: 10000,
  })
  if (verify.status !== 0)
    throw new Error(verify.stderr || "Rehearsal failed")
  process.stdout.write(`${JSON.stringify(bundle, null, 2)}\n`)
  process.stderr.write(`Synthetic interface evidence: ${session.evidence.directory}\n`)
}
finally {
  await session.close()
}

import { mkdtemp, readFile, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { fileURLToPath } from "node:url"
import { bytesDigest, canonical } from "../apps/instrument-interface/src/contract.mjs"

export async function createExample() {
  const path = fileURLToPath(new URL("../apps/instrument-gateway/examples/simulated-reader.html", import.meta.url))
  const definition = {
    schema: "airalogy.browser-interface.v1",
    id: "example.browser-reader",
    target: {
      application: "Airalogy Simulated Reader",
      version: "1.0",
      title: "Airalogy Simulated Reader — no hardware",
      locale: "en-US",
      scope: { kind: "role", role: "main", name: "" },
      source: { kind: "file", path, sha256: bytesDigest(await readFile(path)) },
      identity: { locator: { kind: "test_id", name: "software-version" }, text: "Airalogy Simulated Reader 1.0 (simulation)" },
    },
    network: [],
    controls: [
      { id: "sample.count", locator: { kind: "role", role: "spinbutton", name: "Synthetic sample count" }, read: "value", operations: ["read", "fill"] },
      { id: "measurement.start", locator: { kind: "role", role: "button", name: "Run simulation" }, read: "text", operations: ["click"] },
      { id: "result.value", locator: { kind: "role", role: "status", name: "Synthetic result" }, read: "text", operations: ["read"] },
      { id: "status", locator: { kind: "test_id", name: "reader-status" }, read: "text", operations: ["read"] },
    ],
    states: [
      { id: "ready", checks: [{ control_id: "status", equals: "Ready" }] },
      { id: "completed", checks: [{ control_id: "status", equals: "Simulation complete" }] },
    ],
    blocked: [],
    privacy: { redact: [], screenshot: true },
    limits: { duration_seconds: 60, max_steps: 3, step_timeout_ms: 5000, viewport: { width: 960, height: 720 } },
  }
  const plan = {
    schema: "airalogy.interface-plan.v1",
    steps: [
      { operation: "fill", control_id: "sample.count", value: "2", before: "ready", after: "ready" },
      { operation: "click", control_id: "measurement.start", before: "ready", after: "completed" },
      { operation: "read", control_id: "result.value", before: "completed", after: "completed" },
    ],
  }
  return { definition, plan }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = await mkdtemp(join(tmpdir(), "airalogy-interface-example-"))
  const example = await createExample()
  example.policy = { goal: "Read two synthetic samples", actions: example.plan.steps, success: [{ control_id: "result.value", equals: "0.84" }] }
  for (const name of ["definition", "plan", "policy"])
    await writeFile(join(root, `${name}.json`), `${canonical(example[name])}\n`, { flag: "wx", mode: 0o600 })
  process.stdout.write(`${canonical({ definition: join(root, "definition.json"), plan: join(root, "plan.json"), policy: join(root, "policy.json"), evidence: root })}\n`)
}

import { mkdtemp, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { bytesDigest, SCHEMA } from "../src/contract.mjs"

export const html = `<!doctype html><html><head><meta charset="UTF-8"><title>Synthetic interface</title></head><body>
<main aria-label="Simulator">
<h1>Simulated Reader 1.0 — no hardware</h1>
<label>Sample count <input type="number" value="1" id="count" data-testid="count"></label>
<button id="run">Run simulation</button>
<output data-testid="result">0</output><p role="status" data-testid="status">Ready</p>
<div data-testid="private">PRIVATE-SYNTHETIC-CONTENT</div>
</main><script>
document.querySelector('#run').onclick = () => {
  document.querySelector('[data-testid=result]').textContent = String(Number(document.querySelector('#count').value) * 0.42);
  document.querySelector('[role=status]').textContent = 'Complete';
};
</script></body></html>`

export function definition(source) {
  return {
    schema: SCHEMA,
    id: "synthetic.reader",
    target: { application: "Synthetic reader", version: "1.0", title: "Synthetic interface", locale: "en-US", scope: { kind: "role", role: "main", name: "Simulator" }, source, identity: { locator: { kind: "role", role: "heading", name: "Simulated Reader 1.0 — no hardware" }, text: "Simulated Reader 1.0 — no hardware" } },
    network: source.kind === "url" ? [{ url: source.url, method: "GET", max_requests: 1 }] : [],
    controls: [
      { id: "count", locator: { kind: "role", role: "spinbutton", name: "Sample count" }, read: "value", operations: ["read", "fill"] },
      { id: "run", locator: { kind: "role", role: "button", name: "Run simulation" }, read: "text", operations: ["click"] },
      { id: "result", locator: { kind: "test_id", name: "result" }, read: "text", operations: ["read"] },
      { id: "status", locator: { kind: "test_id", name: "status" }, read: "text", operations: ["read"] },
    ],
    states: [{ id: "ready", checks: [{ control_id: "status", equals: "Ready" }] }, { id: "complete", checks: [{ control_id: "status", equals: "Complete" }] }],
    blocked: [],
    privacy: { redact: [{ kind: "test_id", name: "private" }], screenshot: false },
    limits: { duration_seconds: 30, max_steps: 5, step_timeout_ms: 5000, viewport: { width: 800, height: 600 } },
  }
}
export const plan = {
  schema: "airalogy.interface-plan.v1",
  steps: [
    { operation: "fill", control_id: "count", value: "2", before: "ready", after: "ready" },
    { operation: "click", control_id: "run", before: "ready", after: "complete" },
    { operation: "read", control_id: "result", before: "complete", after: "complete" },
  ],
}
export const emptyPlan = { schema: "airalogy.interface-plan.v1", steps: [] }
export async function fixture(content = html) {
  const root = await mkdtemp(join(tmpdir(), "airalogy-interface-test-"))
  const path = join(root, "synthetic.html")
  await writeFile(path, content, { mode: 0o600 })
  return { root, definition: definition({ kind: "file", path, sha256: bytesDigest(content) }) }
}

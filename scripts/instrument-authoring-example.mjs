// Generate selected synthetic inputs from the single reference fixture; no AI or device access.
import { closeSync, fsyncSync, openSync, readFileSync, writeFileSync } from "node:fs"
import { fileURLToPath } from "node:url"

if (process.argv.length !== 3)
  throw new Error("Usage: node scripts/instrument-authoring-example.mjs /absolute/new-spec.json")
const root = new URL("../apps/instrument-gateway/examples/adapter-package/", import.meta.url)
const selected = name => readFileSync(new URL(name, root), "utf8")
const manifest = JSON.parse(selected("manifest.json"))
manifest.provenance.kind = "aira"
const spec = {
  goal: "Implement the synthetic reader only; no instrument connection or hardware qualification",
  manifest,
  factory: "synthetic_reader:create_adapter",
  materials: [{ name: "synthetic-contract.txt", text: "Return round(0.42 * sample_count, 2), unit synthetic_unit and simulation_only true. Accept only integer sample_count 1..96, not bool. Reject unknown commands, reject a set stop_event. No physical process, networking, files or configuration. The fixed tests define synthetic completion; never claim real hardware support." }],
  tests: { "tests/test_reader.py": selected("tests/test_reader.py") },
  licenses: { "licenses/LICENSE.txt": selected("licenses/LICENSE.txt") },
  initial_sources: {},
}
const output = process.argv[2]
if (!output.startsWith("/") || output.endsWith("/"))
  throw new Error("Choose a new absolute file path")
const fd = openSync(output, "wx", 0o600)
try {
  writeFileSync(fd, `${JSON.stringify(spec, null, 2)}\n`)
  fsyncSync(fd)
}
finally { closeSync(fd) }
process.stdout.write(`Synthetic-only authoring inputs: ${output}\nReference: ${fileURLToPath(root)}\n`)

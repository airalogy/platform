import { readFileSync, writeFileSync } from "node:fs"
import { fileURLToPath } from "node:url"

const root = new URL("../", import.meta.url)
const source = new URL("apps/instrument-gateway/src/airalogy_instrument_gateway/integration_contract.py", root)
const target = new URL("apps/api/app/services/instrument_adapter_contract.py", root)
const content = readFileSync(source, "utf8")
if (process.argv.includes("--check")) {
  if (readFileSync(target, "utf8") !== content)
    throw new Error("Instrument contract is out of sync; run node scripts/sync-instrument-contract.mjs")
}
else {
  writeFileSync(fileURLToPath(target), content)
}

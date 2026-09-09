import { readFileSync, writeFileSync } from "node:fs"
import { fileURLToPath } from "node:url"

const root = new URL("../", import.meta.url)
for (const [sourceName, targetName] of [
  ["integration_contract.py", "instrument_adapter_contract.py"],
  ["package_contract.py", "instrument_package_contract.py"],
  ["installation_contract.py", "instrument_installation_contract.py"],
  ["activation_contract.py", "instrument_activation_contract.py"],
  ["output_contract.py", "instrument_output_contract.py"],
]) {
  const source = new URL(`apps/instrument-gateway/src/airalogy_instrument_gateway/${sourceName}`, root)
  const target = new URL(`apps/api/app/services/${targetName}`, root)
  const content = readFileSync(source, "utf8")
  if (process.argv.includes("--check")) {
    if (readFileSync(target, "utf8") !== content)
      throw new Error("Instrument contract is out of sync; run node scripts/sync-instrument-contract.mjs")
  }
  else {
    writeFileSync(fileURLToPath(target), content)
  }
}

import { readFileSync, writeFileSync } from "node:fs"
import { fileURLToPath } from "node:url"

const root = new URL("../", import.meta.url)
for (const [sourceName, targetName] of [
  ["integration_contract.py", "instrument_adapter_contract.py"],
  ["package_contract.py", "instrument_package_contract.py"],
  ["installation_contract.py", "instrument_installation_contract.py"],
  ["activation_contract.py", "instrument_activation_contract.py"],
  ["output_contract.py", "instrument_output_contract.py"],
  ["authoring_contract.py", "instrument_authoring_contract.py"],
]) {
  const source = new URL(`apps/instrument-gateway/src/airalogy_instrument_gateway/${sourceName}`, root)
  const target = new URL(`apps/api/app/services/${targetName}`, root)
  const content = readFileSync(source, "utf8").replace("from .package_contract import (", "from .instrument_package_contract import (")
  if (process.argv.includes("--check")) {
    if (readFileSync(target, "utf8") !== content)
      throw new Error("Instrument contract is out of sync; run node scripts/sync-instrument-contract.mjs")
  }
  else {
    writeFileSync(fileURLToPath(target), content)
  }
}

// Browser and API validators consume one authored JSON Schema.
const explorationSchema = readFileSync(new URL("apps/instrument-interface/src/exploration.schema.json", root), "utf8")
const explorationTarget = new URL("apps/api/app/services/instrument_exploration.schema.json", root)
if (process.argv.includes("--check")) {
  if (readFileSync(explorationTarget, "utf8") !== explorationSchema)
    throw new Error("Interface exploration schema is out of sync")
}
else {
  writeFileSync(fileURLToPath(explorationTarget), explorationSchema)
}

const surveySchema = readFileSync(new URL("apps/instrument-interface/src/survey.schema.json", root), "utf8")
const surveyTarget = new URL("apps/api/app/services/instrument_survey.schema.json", root)
if (process.argv.includes("--check")) {
  if (readFileSync(surveyTarget, "utf8") !== surveySchema)
    throw new Error("Interface survey schema is out of sync")
}
else {
  writeFileSync(fileURLToPath(surveyTarget), surveySchema)
}

import { spawn } from "node:child_process"
import { fileURLToPath } from "node:url"
import { prepareComputeTestImage } from "./compute-runner-integration.mjs"

// The shared local/CI gate must actually execute the sealed analysis source,
// not silently skip it because the opt-in image variables were omitted.
const engineEnvironment = prepareComputeTestImage()
const selected = process.argv.slice(2)
if (selected[0] === "--")
  selected.shift()
const child = spawn("bash", ["tests/e2e/scripts/research-integration.sh", ...selected], {
  cwd: fileURLToPath(new URL("../", import.meta.url)),
  stdio: "inherit",
  env: { ...process.env, ...engineEnvironment },
})
child.on("error", (error) => {
  console.error(error.message)
  process.exitCode = 1
})
child.on("exit", (code, signal) => {
  process.exitCode = code ?? (signal === "SIGINT" ? 130 : 1)
})

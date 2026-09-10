import { Buffer } from "node:buffer"
import { canonical } from "./contract.mjs"
import { collectNativeApplications } from "./native-discovery.mjs"

async function main() {
  let input = Buffer.alloc(0)
  for await (const chunk of process.stdin) {
    if (input.length + chunk.length > 16384)
      throw new Error("Bound exceeded")
    input = Buffer.concat([input, chunk])
  }
  const report = await collectNativeApplications(JSON.parse(input.toString("utf8")))
  process.stdout.write(`${canonical(report)}\n`)
}
main().catch(() => {
  // Never forward directory names, metadata or underlying OS/parser errors.
  process.exitCode = 1
})

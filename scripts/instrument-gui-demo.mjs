// Actual browser interaction with a bundled synthetic application, never a device.
// Prints an importable rehearsal bundle. No target URL or executable input is accepted.
import { spawnSync } from "node:child_process"
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { chromium } from "@playwright/test"

const root = new URL("../", import.meta.url)
const target = { application: "Airalogy Simulated Reader", version: "1.0", os: "simulation", locale: "en-US" }
const browser = await chromium.launch({ headless: !process.argv.includes("--headed") })
try {
  const context = await browser.newContext({ viewport: { width: 960, height: 720 } })
  // Deny every network request, even if the synthetic fixture is later changed.
  await context.route("**/*", route => route.abort())
  const page = await context.newPage()
  await page.setContent(readFileSync(new URL("apps/instrument-gateway/examples/simulated-reader.html", root), "utf8"))
  const steps = [
    { operation: "set_value", control_id: "sample.count", value: 2, before: "ready", after: "ready" },
    { operation: "invoke", control_id: "measurement.start", before: "ready", after: "completed" },
    { operation: "read", control_id: "result.value", output_key: "value", before: "completed", after: "completed" },
  ]
  async function observe() {
    const state = await page.locator("main").evaluate(element => ({
      state: element.dataset.state,
      session: element.dataset.session,
      control_owner: element.dataset.owner,
    }))
    const controls = await page.locator("[data-control]").evaluateAll(elements => elements.map(element => ({
      id: element.dataset.control,
      enabled: !element.disabled,
      value: element.tagName === "INPUT" ? Number(element.value) : element.tagName === "OUTPUT" ? Number(element.textContent) : element.textContent.trim(),
    })))
    return { target, window_id: "synthetic-reader-window", ...state, blocking_dialog: await page.getByRole("alertdialog").isVisible(), controls }
  }
  const observations = []
  for (const step of steps) {
    observations.push(await observe())
    const control = page.locator(`[data-control="${step.control_id}"]`)
    if (await control.count() !== 1)
      throw new Error("Control identity is ambiguous")
    if (step.operation === "set_value")
      await control.fill(String(step.value))
    if (step.operation === "invoke")
      await control.click()
    observations.push(await observe())
  }
  const bundle = {
    package: {
      schema: "airalogy.gui-rehearsal.v1",
      id: "example.browser-reader",
      version: "v1",
      target,
      source: { kind: "demonstration", reference: "Bundled synthetic browser demonstration" },
      limitations: ["Only the bundled synthetic application was exercised. No OS desktop or hardware qualification."],
      commands: [{ key: "measure.synthetic", version: "v1", name: "Synthetic measurement", steps }],
    },
    scenarios: [{ name: "Two synthetic samples", command_key: "measure.synthetic", command_version: "v1", window_id: "synthetic-reader-window", observations, expected_output: { value: 0.84 } }],
  }
  // Expected output is fixed independently of what the browser actually returned.
  const verify = spawnSync("python3", ["-c", "import json,sys; from airalogy_instrument_gateway.integration_contract import rehearse; b=json.load(sys.stdin); r=rehearse(b['package'],b['scenarios']); assert r['passed'],r"], {
    cwd: fileURLToPath(root),
    env: { ...process.env, PYTHONPATH: fileURLToPath(new URL("apps/instrument-gateway/src", root)) },
    input: JSON.stringify(bundle),
    encoding: "utf8",
  })
  if (verify.status !== 0)
    throw new Error(verify.stderr || "Rehearsal failed")
  process.stdout.write(`${JSON.stringify(bundle, null, 2)}\n`)
}
finally {
  await browser.close()
}

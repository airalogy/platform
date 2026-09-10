import type { ChildProcess } from "node:child_process"
import { execFileSync, spawn } from "node:child_process"
import { createHash, randomUUID } from "node:crypto"
import { once } from "node:events"
import { mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

test("local setup browser pairs, exports public request, installs via actual Platform and restores state without starting a driver", async ({ page, request }, testInfo) => {
  const fixtures = await loadFixtures()
  const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
  const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  expect(login.ok()).toBeTruthy()
  const headers = { "Auth-Token": (await login.json()).token }
  async function call(route: string, data?: unknown) {
    const response = await request.fetch(api + route, { method: data === undefined ? "GET" : "POST", headers, data })
    expect(response.ok(), await response.text()).toBeTruthy()
    return response.json()
  }
  async function confirm(route: string, data: Record<string, unknown>) {
    const preview = await call(`${route}/preview`, data)
    return call(route, { ...data, preview_digest: preview.preview_digest })
  }
  const directory = await realpath(await mkdtemp(path.join(os.tmpdir(), "airalogy-local-setup-")))
  let child: ChildProcess | undefined
  try {
    const suffix = Date.now()
    const base = `/labs/${fixtures.lab.id}/resource-library`
    const definitions = await call(`${base}/definition-versions`)
    const definition = definitions.items.find((item: { protocol_uid: string }) => item.protocol_uid === "plasmid_resource_definition_en")
    const kind = await call(`${base}/types`, { protocol_version_id: definition.id, code: `setup_${suffix}`, name: "Synthetic setup fixture", capabilities: { booking: true }, booking_policy: "auto" })
    const equipment = await call(`${base}/resources`, { resource_type_id: kind.id, name: `Setup reader ${suffix}`, code: `SETUP-${suffix}`, visibility: "lab", data: { construct_name: "Synthetic fixture", aliases: null, backbone: null, sequence: null, sequence_file: null, resistance_markers: null, host_species: null, copy_number: null, external_source: null, features: [] } })
    const gateway = (await confirm("/research-instrument-gateways", { lab_id: fixtures.lab.id, name: `Setup gateway ${suffix}`, enabled: false })).gateway
    const pairing = await confirm("/instrument-pairings", { gateway_id: gateway.id, expected_revision: gateway.revision, reason: "Synthetic local browser acceptance" })
    const source = "apps/instrument-gateway/examples/adapter-package"
    const archive = path.join(directory, "synthetic.zip")
    const env = { ...process.env, PYTHONPATH: "apps/instrument-gateway/src:apps/instrument-gateway/tests" }
    execFileSync("python3", ["-m", "airalogy_instrument_gateway.package_cli", "build", "--manifest", `${source}/manifest.json`, "--factory", "synthetic_reader:create_adapter", "--file", `source/synthetic_reader.py=${source}/source/synthetic_reader.py`, "--file", `tests/test_reader.py=${source}/tests/test_reader.py`, "--file", `licenses/LICENSE.txt=${source}/licenses/LICENSE.txt`, "--output", archive], { env })
    const raw = await readFile(archive)
    const wheel = execFileSync("python3", ["-c", "import sys; from test_package_installation import sdk; sys.stdout.buffer.write(sdk())"], { env })
    const wheelPath = path.join(directory, "gateway.whl")
    const configPath = path.join(directory, "private-config.json")
    await writeFile(wheelPath, wheel)
    await writeFile(configPath, "{\"private_secret\":\"NEVER-SEND-THIS-CONFIG\"}")
    child = spawn("python3", ["-m", "airalogy_instrument_gateway.setup_cli", "--root", directory], { env, stdio: ["ignore", "pipe", "pipe"] })
    const localUrl = await new Promise<string>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("Local setup did not start")), 10000)
      let output = ""
      child!.stdout!.on("data", (chunk) => {
        output += chunk.toString()
        const match = output.match(/http:\/\/127\.0\.0\.1:\d+\/#[\w-]+/)
        if (match) {
          clearTimeout(timer)
          resolve(match[0])
        }
      })
      child!.once("error", reject)
    })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(localUrl)
    await expect(page.locator("#root")).toHaveText(directory)
    await page.locator("#language").selectOption("en")
    for (const [name, value] of Object.entries({ platform_url: api, lab_id: fixtures.lab.id, gateway_id: gateway.id, client_name: "Synthetic setup station" }))
      await page.locator(`[name="${name}"]`).fill(value)
    await page.getByRole("button", { name: "Review local identity", exact: true }).click()
    await expect(page.locator("#impact")).toContainText(gateway.id)
    await expect(page.locator("#confirm")).toBeDisabled()
    await page.locator("#reviewed").check()
    await page.locator("#confirm").click()
    await expect(page.locator("#scope")).toContainText(gateway.id)
    await page.locator("#pair-code").fill(pairing.code)
    await page.getByRole("button", { name: "Claim this code", exact: true }).click()
    await expect(page.locator("#pair-result")).toContainText("fingerprint")
    const paired = JSON.parse((await page.locator("#pair-result").textContent())!)
    const pairPreview = await call(`/instrument-pairings/${pairing.pairing.id}/preview`, {})
    expect(pairPreview.pairing.fingerprint).toBe(paired.fingerprint)
    await call(`/instrument-pairings/${pairing.pairing.id}/confirm`, { preview_digest: pairPreview.preview_digest })
    await page.locator("#pair-status").click()
    await expect(page.locator("#pair-result")).toContainText("confirmed")
    for (const [kind, file] of Object.entries({ package: archive, sdk_wheel: wheelPath, config: configPath })) {
      await page.locator(`[data-kind="${kind}"]`).setInputFiles(file)
      await expect(page.locator(`#${kind}-info`)).toContainText("Private local copy saved")
    }
    await page.locator("#sdk-digest").fill(createHash("sha256").update(wheel).digest("hex"))
    await page.getByRole("button", { name: "Preview installation inputs", exact: true }).click()
    await expect(page.locator("#impact")).toContainText("\"hardware_authorized\": false")
    await expect(page.locator("#impact")).not.toContainText("NEVER-SEND-THIS-CONFIG")
    await page.locator("#reviewed").check()
    await page.locator("#confirm").click()
    await expect(page.locator("#install-result")).toContainText("airalogy.installation-request.v1")
    await page.reload()
    await expect(page.locator("#requests option")).toHaveCount(2)
    const downloading = page.waitForEvent("download")
    await page.locator("#download").click()
    const downloaded = await downloading
    const publicText = await readFile((await downloaded.path())!, "utf8")
    const publicRequest = JSON.parse(publicText)
    expect(publicText).not.toMatch(/installation_token|gateway_token|NEVER-SEND-THIS-CONFIG/)
    expect(publicText).not.toContain(directory)
    const releaseId = randomUUID()
    const upload = { headers: { ...headers, "Content-Type": "application/zip" }, params: { lab_id: fixtures.lab.id, request_id: releaseId }, data: raw }
    const importPreview = await (await request.post(`${api}/instrument-adapter-packages/preview`, upload)).json()
    const imported = await request.post(`${api}/instrument-adapter-packages`, { ...upload, headers: { ...upload.headers, "X-Airalogy-Preview-Digest": importPreview.preview_digest } })
    expect(imported.ok(), await imported.text()).toBeTruthy()
    await confirm(`/instrument-adapter-packages/${releaseId}/review`, { expected_revision: 1, operation: "approve_source", reason: "Synthetic setup source review; no equipment approval", source_reviewed: true })
    await confirm("/instrument-installations", { request: publicRequest, resource_id: equipment.id, release_id: releaseId, reason: "Synthetic local setup acceptance", fingerprint_confirmed: true })
    await page.locator("#install-status").click()
    await expect(page.locator("#impact")).toContainText("\"state\": \"authorized\"")
    await expect(page.locator("#confirm")).toBeDisabled()
    await page.locator("#reviewed").check()
    await page.locator("#confirm").click()
    await expect(page.locator("#install-result")).toContainText("\"state\": \"installed\"")
    await expect(page.locator("#install-result")).toContainText("\"activation_performed\": false")
    await page.locator("#language").selectOption("zh")
    await expect(page.getByRole("heading", { name: "本地设备接入向导" })).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath("local-setup-mobile.png"), fullPage: true })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const bindings = await call(`/instrument-installations?gateway_id=${gateway.id}`)
    expect(bindings.items[0].state).toBe("installed")
    expect((await call(`/research-instrument-gateways/${gateway.id}/commands`)).items).toEqual([])
    const gateways = await call(`/research-instrument-gateways?lab_id=${fixtures.lab.id}`)
    expect(gateways.items.find((item: { id: string }) => item.id === gateway.id).enabled).toBe(false)
  }
  finally {
    if (child && child.exitCode === null) {
      const exited = once(child, "exit")
      child.kill("SIGTERM")
      await exited
    }
    await rm(directory, { recursive: true, force: true })
  }
})

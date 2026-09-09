import { execFileSync } from "node:child_process"
import { createHash, randomBytes, randomUUID } from "node:crypto"
import { mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

test("installation UI confirms exact identity, rejects private files and preserves revocation history", async ({ page, request }) => {
  const fixtures = await loadFixtures()
  const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
  const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  const headers = { "Auth-Token": (await login.json()).token }
  async function call(route: string, data: unknown, method = "POST") {
    const response = await request.fetch(api + route, { method, headers, data })
    expect(response.ok(), await response.text()).toBeTruthy()
    return response.json()
  }
  async function confirm(route: string, data: Record<string, unknown>) {
    const preview = await call(`${route}/preview`, data)
    return call(route, { ...data, preview_digest: preview.preview_digest })
  }
  const directory = await realpath(await mkdtemp(path.join(os.tmpdir(), "airalogy-install-e2e-")))
  try {
    const suffix = Date.now()
    const base = `/labs/${fixtures.lab.id}/resource-library`
    const definitions = await call(`${base}/definition-versions`, undefined, "GET")
    const definition = definitions.items.find((item: { protocol_uid: string }) => item.protocol_uid === "plasmid_resource_definition_en")
    const kind = await call(`${base}/types`, { protocol_version_id: definition.id, code: `install_${suffix}`, name: "Synthetic install equipment", capabilities: { booking: true }, booking_policy: "approval" })
    await call(`${base}/resources`, { resource_type_id: kind.id, name: `Install Reader ${suffix}`, code: `INSTALL-${suffix}`, visibility: "lab", data: { construct_name: "Synthetic fixture", aliases: null, backbone: null, sequence: null, sequence_file: null, resistance_markers: null, host_species: null, copy_number: null, external_source: null, features: [] } })
    const gateway = (await confirm("/research-instrument-gateways", { lab_id: fixtures.lab.id, name: `Install gateway ${suffix}`, enabled: false })).gateway
    const pairing = await confirm("/instrument-pairings", { gateway_id: gateway.id, expected_revision: gateway.revision, reason: "Synthetic UI pairing" })
    const token = `aigw_${randomBytes(32).toString("base64url")}`
    await call("/instrument-pairings/claim", { code: pairing.code, gateway_id: gateway.id, lab_id: fixtures.lab.id, client_name: "Synthetic installer station", credential_digest: createHash("sha256").update(token).digest("hex"), credential_hint: token.slice(-8) })
    const pairPreview = await call(`/instrument-pairings/${pairing.pairing.id}/preview`, {})
    await call(`/instrument-pairings/${pairing.pairing.id}/confirm`, { preview_digest: pairPreview.preview_digest })
    const source = "apps/instrument-gateway/examples/adapter-package"
    const manifest = JSON.parse(await readFile(`${source}/manifest.json`, "utf8"))
    manifest.id = `synthetic.installation.${suffix}`
    await writeFile(path.join(directory, "manifest.json"), JSON.stringify(manifest))
    const archive = path.join(directory, "synthetic.zip")
    const env = { ...process.env, PYTHONPATH: "apps/instrument-gateway/src:apps/instrument-gateway/tests" }
    execFileSync("python3", ["-m", "airalogy_instrument_gateway.package_cli", "build", "--manifest", path.join(directory, "manifest.json"), "--factory", "synthetic_reader:create_adapter", "--file", `source/synthetic_reader.py=${source}/source/synthetic_reader.py`, "--file", `tests/test_reader.py=${source}/tests/test_reader.py`, "--file", `licenses/LICENSE.txt=${source}/licenses/LICENSE.txt`, "--output", archive], { env })
    const raw = await readFile(archive)
    const releaseId = randomUUID()
    const url = `${api}/instrument-adapter-packages`
    const upload = { headers: { ...headers, "Content-Type": "application/zip" }, params: { lab_id: fixtures.lab.id, request_id: releaseId }, data: raw }
    const preview = await (await request.post(`${url}/preview`, upload)).json()
    const imported = await request.post(url, { ...upload, headers: { ...upload.headers, "X-Airalogy-Preview-Digest": preview.preview_digest } })
    expect(imported.ok(), await imported.text()).toBeTruthy()
    await confirm(`/instrument-adapter-packages/${releaseId}/review`, { expected_revision: 1, operation: "approve_source", reason: "Reviewed synthetic package", source_reviewed: true })
    // Generate a real local request without executing adapter or hardware code.
    const publicRequest = JSON.parse(execFileSync("python3", ["-c", "import sys,json; from pathlib import Path; from test_package_installation import sdk; from airalogy_instrument_gateway.package_contract import sha256; from airalogy_instrument_gateway.installation_manager import prepare; root=Path(sys.argv[1]); wheel=sdk(); (root/'sdk.whl').write_bytes(wheel); (root/'config.json').write_text('{}'); print(json.dumps(prepare(destination=root/'private.json', platform_url=sys.argv[2], lab_id=sys.argv[3], gateway_id=sys.argv[4], package=root/'synthetic.zip', sdk_wheel=root/'sdk.whl', trusted_sdk_digest=sha256(wheel), config=root/'config.json', root=root)))", directory, api, fixtures.lab.id, gateway.id], { env, encoding: "utf8" }))
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(`/labs/${fixtures.lab.uid}/resources/gateways`)
    await page.locator(".gateway-card__main").filter({ hasText: gateway.name }).click()
    const panel = page.getByTestId("instrument-installations-panel")
    await panel.getByRole("button", { name: "Authorize an installation" }).click()
    let modal = page.getByRole("dialog").last()
    const input = page.getByTestId("installation-request").locator("textarea")
    await input.fill(JSON.stringify({ ...publicRequest, installation_token: "should-not-be-transmitted" }))
    await expect(modal).toContainText("Private credentials and unexpected fields are not accepted")
    await expect(modal.getByRole("button", { name: "Preview", exact: true })).toBeDisabled()
    await input.fill(JSON.stringify(publicRequest))
    await page.getByTestId("installation-equipment").click()
    await selectVisibleOption(page, `Install Reader ${suffix}`)
    await page.getByTestId("installation-reason").locator("textarea").fill("Synthetic installation authorization")
    await expect(modal.getByRole("button", { name: "Preview", exact: true })).toBeDisabled()
    await modal.getByRole("checkbox").check()
    await modal.getByRole("button", { name: "Preview", exact: true }).click()
    await expect(modal).toContainText(publicRequest.descriptor.archive_digest)
    await expect(modal).toContainText("revoking the grant does not restore manual execution")
    await expect(modal).toContainText("That activation stage is not yet available")
    expect((await modal.boundingBox())!.width).toBeLessThanOrEqual(358)
    await modal.getByRole("button", { name: "Confirm", exact: true }).click()
    await expect(panel).toContainText("Authorized, awaiting local claim")
    await page.reload()
    await page.locator(".gateway-card__main").filter({ hasText: gateway.name }).click()
    await panel.getByRole("button", { name: "Inspect and review" }).click()
    modal = page.getByRole("dialog").last()
    await expect(modal).toContainText("Synthetic installation authorization")
    await modal.locator("textarea").fill("Cancel synthetic authorization")
    await modal.getByRole("button", { name: "Preview installation revocation" }).click()
    await expect(modal).toContainText("does not uninstall software")
    await modal.getByRole("button", { name: "Confirm", exact: true }).click()
    await expect(panel).toContainText("Authorization revoked")
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    const gateways = await call(`/research-instrument-gateways?lab_id=${fixtures.lab.id}`, undefined, "GET")
    const current = gateways.items.find((item: { id: string }) => item.id === gateway.id)
    expect(current.enabled).toBe(false)
    // Cancellation before local claim does not permanently opt into managed execution.
    const update = { expected_revision: current.revision, name: current.name, description: current.description, enabled: true, reason: "Unclaimed synthetic grant was cancelled" }
    const enabledPreview = await call(`/research-instrument-gateways/${current.id}/preview`, update)
    const enabled = await call(`/research-instrument-gateways/${current.id}`, { ...update, preview_digest: enabledPreview.preview_digest }, "PUT")
    expect(enabled.enabled).toBe(true)
    const stop = { ...update, expected_revision: enabled.revision, enabled: false }
    const stopPreview = await call(`/research-instrument-gateways/${current.id}/preview`, stop)
    await call(`/research-instrument-gateways/${current.id}`, { ...stop, preview_digest: stopPreview.preview_digest }, "PUT")
  }
  finally {
    await rm(directory, { recursive: true, force: true })
  }
})

import { randomUUID } from "node:crypto"
import { readFile } from "node:fs/promises"
import { expect, test } from "@playwright/test"
import { instrumentWorkspaceUrl, loadFixtures, selectVisibleOption } from "./fixtures"

for (const risk of ["read_only", "medium"]) {
  test(`authoring UI ${risk} contract fixtures: private-file rejection, confirmation, history and AI-off fallback`, async ({ page, request }, testInfo) => {
  // Real resource/Gateway permissions; authoring responses below are UI fixtures.
  // Actual authoring transactions/provider-response validation run in research:integration.
    const fixtures = await loadFixtures()
    const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
    const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    const headers = { "Auth-Token": (await login.json()).token }
    async function call(route: string, data?: unknown) {
      const response = await request.fetch(api + route, { method: data === undefined ? "GET" : "POST", headers, data })
      expect(response.ok(), await response.text()).toBeTruthy()
      return response.json()
    }
    const suffix = Date.now()
    const base = `/labs/${fixtures.lab.id}/resource-library`
    const definitions = await call(`${base}/definition-versions`)
    const definition = definitions.items.find((item: { protocol_uid: string }) => item.protocol_uid === "plasmid_resource_definition_en")
    const kind = await call(`${base}/types`, { protocol_version_id: definition.id, code: `author_${suffix}`, name: "Synthetic authoring fixture", capabilities: { booking: true }, booking_policy: "auto" })
    const equipment = await call(`${base}/resources`, { resource_type_id: kind.id, name: `Author Reader ${suffix}`, code: `AUTHOR-${suffix}`, visibility: "lab", data: { construct_name: "Synthetic fixture", aliases: null, backbone: null, sequence: null, sequence_file: null, resistance_markers: null, host_species: null, copy_number: null, external_source: null, features: [] } })
    const draft = { lab_id: fixtures.lab.id, name: `Author gateway ${suffix}`, enabled: false }
    const gatewayPreview = await call("/research-instrument-gateways/preview", draft)
    const gateway = (await call("/research-instrument-gateways", { ...draft, preview_digest: gatewayPreview.preview_digest })).gateway
    const source = "apps/instrument-gateway/examples/adapter-package"
    const manifest = JSON.parse(await readFile(`${source}/manifest.json`, "utf8"))
    manifest.provenance.kind = "aira"
    manifest.commands[0].risk = risk
    manifest.commands[0].device_confirmation_required = risk === "medium"
    const selected = {
      schema: "airalogy.authoring-request.v1",
      id: randomUUID(),
      gateway_id: gateway.id,
      resource_id: equipment.id,
      credential_digest: "1".repeat(64),
      fingerprint: "2".repeat(64),
      max_iterations: 3,
      duration_seconds: 900,
      sandbox: { sdk_digest: "3".repeat(64), image: `sha256:${"4".repeat(64)}`, timeout_seconds: 60 },
      spec: { goal: "Synthetic source authoring UI acceptance", factory: "synthetic_reader:create_adapter", manifest, materials: [{ name: "synthetic.txt", text: "Synthetic fixed contract only" }], tests: { "tests/test_reader.py": await readFile(`${source}/tests/test_reader.py`, "utf8") }, licenses: { "licenses/LICENSE.txt": await readFile(`${source}/licenses/LICENSE.txt`, "utf8") }, initial_sources: {} },
    }
    let ai = true
    let saved: Record<string, any> | null = null
    let writes = 0
    await page.route("**/api/instance", async (route) => {
      const response = await route.fetch()
      await route.fulfill({ response, json: { ...await response.json(), ai_enabled: ai } })
    })
    await page.route(url => url.pathname === "/api/instrument-authoring" || url.pathname.startsWith("/api/instrument-authoring/"), async (route) => {
      const url = new URL(route.request().url())
      const method = route.request().method()
      if (method === "GET") {
        await route.fulfill({ json: url.pathname.endsWith(selected.id) ? saved : { items: saved ? [{ id: saved.id, goal: selected.spec.goal, state: saved.effective_state, expires_at: saved.expires_at, created_at: new Date().toISOString() }] : [], has_more: false, next_offset: 20 } })
        return
      }
      writes++
      const input = route.request().postDataJSON()
      expect(JSON.stringify(input)).not.toContain("authoring_token")
      if (url.pathname.endsWith("/preview")) {
        expect(input.request).toEqual(selected)
        expect(input.controlled_source_consent).toBe(risk === "medium" ? true : undefined)
        await route.fulfill({ json: { preview_digest: "5".repeat(64), source_review: { requires_controlled_source_consent: risk === "medium", execution_authorized: false, commands: selected.spec.manifest.commands } } })
      }
      else if (url.pathname.endsWith("/cancel")) {
        expect(input.request_fingerprint).toBe(selected.fingerprint)
        saved!.effective_state = "cancelled"
        await route.fulfill({ json: saved })
      }
      else {
        expect(input.preview_digest).toBe("5".repeat(64))
        expect(input.controlled_source_consent).toBe(risk === "medium" ? true : undefined)
        saved = { id: selected.id, request: selected, effective_state: "open", expires_at: new Date(Date.now() + 900000).toISOString(), turns: [] }
        await route.fulfill({ json: saved })
      }
    })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(instrumentWorkspaceUrl(fixtures.lab.uid, gateway.id, equipment.id, "prepare", "author"))
    await page.locator(".gateway-card__main").filter({ hasText: gateway.name }).click()
    const panel = page.getByTestId("instrument-authoring-panel")
    await expect(panel.getByTestId("authoring-local-guide")).toHaveAttribute("href", /\/docs\/en\/architecture\/instrument-source-authoring#local-browser-development-guide$/)
    await panel.getByRole("button", { name: "Authorize Aira development", exact: true }).click()
    let modal = page.getByRole("dialog").last()
    const input = page.getByTestId("authoring-request").locator("textarea")
    await input.fill(JSON.stringify({ ...selected, authoring_token: `aiauthor_${"A".repeat(43)}` }))
    await expect(modal.getByRole("button", { name: "Preview", exact: true })).toBeDisabled()
    expect(writes).toBe(0)
    await input.fill(JSON.stringify(selected))
    await expect(modal.getByTestId("authoring-command-review")).toContainText(risk === "medium" ? "Medium" : "Read only")
    await modal.locator("input:not([type=file])").fill("Reviewed synthetic UI inputs")
    for (const checkbox of await modal.getByRole("checkbox").all()) {
      if (await checkbox.getAttribute("data-testid") !== "authoring-controlled-consent")
        await checkbox.check()
    }
    if (risk === "medium") {
      await expect(modal.getByRole("button", { name: "Preview", exact: true })).toBeDisabled()
      expect(writes).toBe(0)
      await modal.getByTestId("authoring-controlled-consent").check()
      // A replacement input invalidates both general and controlled-source consent.
      await input.fill(`${JSON.stringify(selected)}\n`)
      await expect(modal.getByTestId("authoring-controlled-consent")).not.toBeChecked()
      await expect(modal.getByRole("button", { name: "Preview", exact: true })).toBeDisabled()
      for (const checkbox of await modal.getByRole("checkbox").all())
        await checkbox.check()
    }
    await modal.getByRole("button", { name: "Preview", exact: true }).click()
    await expect(modal).toContainText("It cannot launch software")
    await expect(modal).toContainText(selected.fingerprint)
    expect((await modal.boundingBox())!.width).toBeLessThanOrEqual(358)
    await modal.screenshot({ path: testInfo.outputPath("authoring-preview-mobile.png"), animations: "disabled" })
    await modal.getByRole("button", { name: "Confirm", exact: true }).click()
    modal = page.getByRole("dialog").last()
    await expect(modal).toContainText("Waiting for the local authoring assistant")
    saved!.turns = [{ id: randomUUID(), ordinal: 1, effective_state: "generated", proposal: { summary: "Synthetic draft — not equipment control", sources: { "source/synthetic_reader.py": "<img data-injected src=x onerror=alert(1)>" }, assumptions: [], missing_information: [] }, report: { passed: true, failure_reason: "", untrusted_test_output: "Synthetic fixed tests passed", archive_digest: "6".repeat(64) } }]
    await modal.getByRole("button", { name: "Refresh", exact: true }).click()
    await expect(modal).toContainText("not trusted hardware qualification")
    await modal.getByText("Inspect untrusted source and local test report", { exact: true }).click()
    await expect(modal.locator("pre")).toContainText("<img data-injected")
    await expect(page.locator("[data-injected]")).toHaveCount(0)
    await modal.locator("input").fill("End synthetic session")
    await modal.getByRole("checkbox").check()
    await modal.getByRole("button", { name: "Cancel development authority", exact: true }).click()
    await expect(modal).toContainText("Cancelled")
    await modal.screenshot({ path: testInfo.outputPath("authoring-history-mobile.png"), animations: "disabled" })
    ai = false
    await page.addInitScript(() => {
      localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null }))
    })
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.reload()
    await page.locator(".gateway-card__main").filter({ hasText: gateway.name }).click()
    await expect(panel).toContainText("Aira 当前不可用")
    await expect(panel.getByRole("button", { name: "授权 Aira 开发" })).toHaveCount(0)
    const select = panel.locator(".n-select")
    await select.click()
    await selectVisibleOption(page, equipment.name)
    await expect(panel).toContainText("已取消")
    await panel.screenshot({ path: testInfo.outputPath("authoring-history-zh.png"), animations: "disabled" })
    // Old history responses without source_review still show the fixed contract.
    await panel.getByRole("button", { name: "查看与审核", exact: true }).click()
    modal = page.getByRole("dialog").last()
    const review = modal.getByTestId("authoring-command-review")
    await expect(review).toContainText("指令副作用声明")
    await expect(review).toContainText("要求的完成依据")
    await expect(review.locator(".n-tag")).toHaveText(risk === "medium" ? "中" : "只读")
    await modal.screenshot({ path: testInfo.outputPath("authoring-review-zh.png"), animations: "disabled" })
  })
}

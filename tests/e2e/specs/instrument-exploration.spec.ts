import { randomUUID } from "node:crypto"
import { readFile } from "node:fs/promises"
import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

for (const native of [false, true]) {
  test(`exploration UI fixtures ${native ? "native" : "browser"}: private request rejection, reviewed actions, history and AI-off`, async ({ page, request }, testInfo) => {
  // Resource/Gateway setup uses real permissions; exploration responses here are UI fixtures.
  // Independent actual browser/API/DB acceptance runs in research:integration.
    const fixtures = await loadFixtures()
    const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
    const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    const headers = { "Auth-Token": (await login.json()).token }
    async function call(path: string, data?: unknown) {
      const response = await request.fetch(api + path, { method: data === undefined ? "GET" : "POST", headers, data })
      expect(response.ok(), await response.text()).toBeTruthy()
      return response.json()
    }
    const suffix = Date.now()
    const base = `/labs/${fixtures.lab.id}/resource-library`
    const definitions = await call(`${base}/definition-versions`)
    const definition = definitions.items.find((item: { protocol_uid: string }) => item.protocol_uid === "plasmid_resource_definition_en")
    const kind = await call(`${base}/types`, { protocol_version_id: definition.id, code: `explore_${suffix}`, name: "Synthetic interface fixture", capabilities: { booking: true }, booking_policy: "auto" })
    const equipment = await call(`${base}/resources`, { resource_type_id: kind.id, name: `Explore Reader ${suffix}`, code: `EXPLORE-${suffix}`, visibility: "lab", data: { construct_name: "Synthetic fixture", aliases: null, backbone: null, sequence: null, sequence_file: null, resistance_markers: null, host_species: null, copy_number: null, external_source: null, features: [] } })
    const draft = { lab_id: fixtures.lab.id, name: `Explore gateway ${suffix}`, enabled: false }
    const preview = await call("/research-instrument-gateways/preview", draft)
    const gateway = (await call("/research-instrument-gateways", { ...draft, preview_digest: preview.preview_digest })).gateway
    const selected = JSON.parse(await readFile("apps/instrument-interface/tests/exploration-fixture.json", "utf8"))
    Object.assign(selected, { id: randomUUID(), gateway_id: gateway.id, resource_id: equipment.id })
    if (native)
      selected.spec.target = { application: "org.airalogy.InstrumentInterfaceSimulator", version: "1.0", kind: "native_macos_simulation" }
    let ai = true
    let saved: Record<string, any> | null = null
    let writes = 0
    await page.route("**/api/instance", async (route) => {
      const response = await route.fetch()
      await route.fulfill({ response, json: { ...await response.json(), ai_enabled: ai } })
    })
    await page.route(url => url.pathname === "/api/instrument-exploration" || url.pathname.startsWith("/api/instrument-exploration/"), async (route) => {
      const url = new URL(route.request().url())
      if (route.request().method() === "GET") {
        await route.fulfill({ json: url.pathname.endsWith(selected.id) ? saved : { items: saved ? [{ id: saved.id, goal: selected.spec.goal, state: saved.effective_state, expires_at: saved.expires_at }] : [], has_more: false, next_offset: 20 } })
        return
      }
      writes++
      const input = route.request().postDataJSON()
      expect(JSON.stringify(input)).not.toContain("aiinterface_")
      if (url.pathname.endsWith("/cancel")) {
        expect(input.request_fingerprint).toBe(selected.fingerprint)
        saved!.effective_state = "cancelled"
        await route.fulfill({ json: saved })
        return
      }
      expect(input.request).toEqual(selected)
      expect(input.model_processing_consent).toBe(true)
      expect(input.local_actions_reviewed).toBe(true)
      if (url.pathname.endsWith("/preview")) {
        await route.fulfill({ json: { preview_digest: "a".repeat(64) } })
      }
      else {
        expect(input.preview_digest).toBe("a".repeat(64))
        saved = { id: selected.id, request: selected, effective_state: "open", expires_at: new Date(Date.now() + 600000).toISOString(), turns: [] }
        await route.fulfill({ json: saved })
      }
    })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(`/labs/${fixtures.lab.uid}/resources/gateways`)
    await page.locator(".gateway-card__main").filter({ hasText: gateway.name }).click()
    const panel = page.getByTestId("instrument-exploration-panel")
    await panel.getByRole("button", { name: "Authorize interface exploration", exact: true }).click()
    const modal = page.getByRole("dialog").last()
    const input = page.getByTestId("exploration-request").locator("textarea")
    await input.fill(JSON.stringify({ request: selected, token: `aiinterface_${"A".repeat(43)}` }))
    await expect(modal.getByRole("button", { name: "Preview", exact: true })).toBeDisabled()
    expect(writes).toBe(0)
    await input.fill(JSON.stringify(selected))
    if (native)
      await expect(modal.getByTestId("native-exploration-boundary")).toContainText("cannot enable vendor software control")
    await modal.locator("input:not([type=file])").fill("Reviewed synthetic actions")
    expect(await modal.getByRole("checkbox").count()).toBe(3)
    for (const checkbox of await modal.getByRole("checkbox").all())
      await checkbox.check()
    await modal.getByRole("button", { name: "Preview", exact: true }).click()
    await expect(modal).toContainText("separately confirm")
    await expect(modal).toContainText("16 KiB")
    await expect(modal).not.toContainText("64 KiB")
    await expect(modal).toContainText(selected.fingerprint)
    expect((await modal.boundingBox())!.width).toBeLessThanOrEqual(358)
    await modal.screenshot({ path: testInfo.outputPath("exploration-preview-mobile.png"), animations: "disabled" })
    await modal.getByRole("button", { name: "Confirm", exact: true }).click()
    await expect(modal).toContainText("Waiting for the locally confirmed interface explorer")
    if (native)
      await expect(modal.getByTestId("native-exploration-boundary")).toContainText("exact build, process and focused window")
    saved!.turns = [{ id: randomUUID(), ordinal: 1, effective_state: "generated", input: { observation: { state: "ready" } }, proposal: { kind: "needs_information", action_index: null, summary: "Synthetic observation only", missing_information: ["<img data-injected src=x onerror=alert(1)>"] }, report: null }]
    await modal.getByRole("button", { name: "Refresh", exact: true }).click()
    await expect(modal).toContainText("not equipment qualification")
    await expect(modal).toContainText("<img data-injected")
    await expect(page.locator("[data-injected]")).toHaveCount(0)
    await modal.locator("input").fill("End simulation")
    await modal.getByRole("checkbox").check()
    await modal.getByRole("button", { name: "Cancel development authority", exact: true }).click()
    await expect(modal).toContainText("Closed or cancelled")
    await modal.screenshot({ path: testInfo.outputPath("exploration-history-mobile.png"), animations: "disabled" })
    ai = false
    await page.addInitScript(() => {
      localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null }))
    })
    await page.reload()
    await page.locator(".gateway-card__main").filter({ hasText: gateway.name }).click()
    await expect(panel).toContainText("Aira 已关闭")
    await expect(panel.getByRole("button", { name: "授权界面探索" })).toHaveCount(0)
    await panel.locator(".n-select").click()
    await selectVisibleOption(page, equipment.name)
    await expect(panel).toContainText("已结束或取消")
    if (native) {
      await panel.getByRole("button", { name: "查看与审核", exact: true }).click()
      await expect(page.getByRole("dialog").last().getByTestId("native-exploration-boundary")).toContainText("不能开启厂商软件控制")
    }
    await panel.screenshot({ path: testInfo.outputPath("exploration-history-zh.png"), animations: "disabled" })
  })
}

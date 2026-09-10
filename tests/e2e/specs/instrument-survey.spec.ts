import { readFile } from "node:fs/promises"
import { expect, test } from "@playwright/test"
import { instrumentWorkspaceUrl, loadFixtures, selectVisibleOption } from "./fixtures"

for (const variant of ["browser", "native", "candidates"]) {
  const native = variant === "native"
  const candidates = variant === "candidates"
  test(`survey UI fixtures (${variant}): scoped report review, one-shot result/export, narrow screen and AI-off`, async ({ page, request }, testInfo) => {
  // Real permission-governed resource setup; survey responses below are explicit UI fixtures.
  // The actual API/model-wrapper/Chromium chain is covered in research:integration.
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
    const kind = await call(`${base}/types`, { protocol_version_id: definition.id, code: `survey_${suffix}`, name: "Synthetic survey fixture", capabilities: { booking: true }, booking_policy: "auto" })
    const equipment = await call(`${base}/resources`, { resource_type_id: kind.id, name: `Survey Reader ${suffix}`, code: `SURVEY-${suffix}`, visibility: "lab", data: { construct_name: "Synthetic fixture", aliases: null, backbone: null, sequence: null, sequence_file: null, resistance_markers: null, host_species: null, copy_number: null, external_source: null, features: [] } })
    const draft = { lab_id: fixtures.lab.id, name: `Survey gateway ${suffix}`, enabled: false }
    const preview = await call("/research-instrument-gateways/preview", draft)
    const gateway = (await call("/research-instrument-gateways", { ...draft, preview_digest: preview.preview_digest })).gateway
    const report = JSON.parse(await readFile(`apps/instrument-interface/tests/fixtures/${candidates ? "application-candidates" : "survey"}.json`, "utf8"))
    if (candidates) {
      report.candidates[0].display_name = report.candidates[0].name
      report.candidates[0].name = null
    }
    if (native) {
      report.target.kind = "native_macos"
      for (const control of report.controls) {
        control.role = control.read === "text" ? "AXStaticText" : "AXButton"
        if (control.locator)
          control.locator = { kind: "ax_identifier", role: control.role, name: control.locator.name }
      }
    }
    let ai = true
    let saved: Record<string, any> | null = null
    let attempts = 0
    let writes = 0
    await page.route("**/api/instance", async (route) => {
      const response = await route.fetch()
      await route.fulfill({ response, json: { ...await response.json(), ai_enabled: ai } })
    })
    await page.route(url => url.pathname === "/api/instrument-surveys" || url.pathname.startsWith("/api/instrument-surveys/"), async (route) => {
      const path = new URL(route.request().url()).pathname
      if (route.request().method() === "GET") {
        const data = path.endsWith("/export") ? { schema: candidates ? "airalogy.application-selection-export.v1" : "airalogy.survey-analysis-export.v1", session_id: saved!.id, turn_id: saved!.turns[0].id, capture_digest: "a".repeat(64), analysis: saved!.turns[0].proposal } : path === "/api/instrument-surveys" ? { items: saved ? [{ id: saved.id, goal: saved.request.spec.goal, state: saved.effective_state, expires_at: saved.expires_at }] : [], has_more: false, next_offset: 20 } : saved
        await route.fulfill({ json: data })
        return
      }
      writes++
      const input = route.request().postDataJSON()
      if (path.endsWith("/analyze")) {
        attempts++
        saved!.can_analyze = false
        const turn = { id: input.id, effective_state: "generated", proposal: { summary: "Synthetic software interpretation", features: [{ control_id: "observed.3", interpretation: "<img data-survey-injected src=x onerror=alert(1)>", basis: "inferred", risk: "unknown" }], identity_control: "observed.1", read_controls: ["observed.3"], route: native ? "native_accessibility" : "browser", limitations: ["No hardware qualification"], missing_information: ["Vendor validation needed"] }, error: null }
        const candidateTurn = { id: input.id, effective_state: "generated", proposal: { summary: "Synthetic software interpretation", recommendations: [{ candidate_id: "candidate_1", rationale: "<img data-survey-injected src=x onerror=alert(1)>", evidence_fields: ["display_name", "bundle_id"] }], limitations: ["No hardware qualification"], missing_information: ["Vendor validation needed"] }, error: null }
        saved!.turns = [candidates ? candidateTurn : turn]
        await route.fulfill({ json: saved!.turns[0] })
        return
      }
      if (path.endsWith("/cancel")) {
        expect(input.request_fingerprint).toBe(saved!.request.fingerprint)
        saved!.effective_state = "cancelled"
        saved!.can_analyze = false
        await route.fulfill({ json: saved })
        return
      }
      expect(input.report).toEqual(report)
      expect(input.gateway_id).toBe(gateway.id)
      expect(input.resource_id).toBe(equipment.id)
      expect(input.capture_reviewed).toBe(true)
      expect(input.model_processing_consent).toBe(true)
      if (path.endsWith("/preview")) {
        await route.fulfill({ json: { preview_digest: "b".repeat(64), capture_digest: "a".repeat(64) } })
      }
      else {
        saved = { id: input.id, request: { fingerprint: "c".repeat(64), spec: { report, goal: input.goal } }, effective_state: "open", expires_at: new Date(Date.now() + 300000).toISOString(), can_analyze: true, turns: [] }
        await route.fulfill({ json: saved })
      }
    })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(instrumentWorkspaceUrl(fixtures.lab.uid, gateway.id, equipment.id, "prepare", "survey"))
    await page.locator(".gateway-card__main").filter({ hasText: gateway.name }).click()
    const panel = page.getByTestId("instrument-survey-panel")
    await panel.locator(".n-select").click()
    await selectVisibleOption(page, equipment.name)
    await panel.getByRole("button", { name: candidates ? "Choose software with Aira" : "Review survey with Aira", exact: true }).click()
    const modal = page.getByRole("dialog").last()
    const input = page.getByTestId("survey-report").locator("textarea")
    await input.fill(JSON.stringify({ selection: report, token: `aiinterface_${"A".repeat(43)}` }))
    await expect(modal.getByRole("button", { name: "Preview", exact: true })).toBeDisabled()
    expect(writes).toBe(0)
    await input.fill(JSON.stringify(report))
    await page.getByTestId("survey-goal").locator("input").fill("Interpret selected synthetic software")
    await page.getByTestId("survey-reason").locator("input").fill("Review private synthetic report")
    for (const checkbox of await modal.getByRole("checkbox").all())
      await checkbox.check()
    await modal.getByRole("button", { name: "Preview", exact: true }).click()
    await expect(modal).toContainText("32 KiB")
    await expect(input).toHaveAttribute("readonly", "")
    await expect(input).not.toBeDisabled()
    await expect(modal).toContainText("a".repeat(64))
    expect((await modal.boundingBox())!.width).toBeLessThanOrEqual(358)
    await modal.screenshot({ path: testInfo.outputPath("survey-review-mobile.png"), animations: "disabled" })
    await modal.getByRole("button", { name: "Confirm", exact: true }).click()
    await expect(modal).toContainText("No model attempt yet")
    await modal.getByRole("button", { name: "Analyze once", exact: true }).click()
    await expect(modal).toContainText("Synthetic software interpretation")
    await expect(modal.getByRole("heading", { name: "Analysis saved", exact: true })).toBeVisible()
    await expect(modal).not.toContainText("Source draft saved")
    if (candidates) {
      await expect(modal).toContainText("metadata-based suggestions")
      await expect(modal).toContainText("candidate_1 · Synthetic Reader")
      await expect(modal).toContainText("Display name · Bundle identifier")
      await expect(modal.getByRole("button", { name: /launch|install|execute/i })).toHaveCount(0)
    }
    else {
      await expect(modal).toContainText(native ? "Native Accessibility (read-only macOS)" : "Browser semantics")
      await expect(modal).toContainText("Inferred · Unknown risk")
    }
    await expect(page.locator("[data-survey-injected]")).toHaveCount(0)
    await modal.getByRole("button", { name: "Refresh", exact: true }).click()
    expect(attempts).toBe(1)
    await expect(modal.getByRole("button", { name: "Analyze once", exact: true })).toHaveCount(0)
    const download = page.waitForEvent("download")
    await modal.getByRole("button", { name: "Export reviewed analysis", exact: true }).click()
    const downloaded = await download
    expect(downloaded.suggestedFilename()).toMatch(candidates ? /^instrument-software-candidates-/ : /^instrument-survey-/)
    const exported = JSON.parse(await readFile((await downloaded.path())!, "utf8"))
    expect(exported.schema).toBe(candidates ? "airalogy.application-selection-export.v1" : "airalogy.survey-analysis-export.v1")
    expect(exported.capture_digest).toBe("a".repeat(64))
    await modal.locator("input").fill("Close reviewed synthetic analysis")
    await modal.getByRole("checkbox").check()
    await modal.getByRole("button", { name: "Cancel development authority", exact: true }).click()
    await expect(modal).toContainText("Closed or cancelled")
    await modal.screenshot({ path: testInfo.outputPath("survey-result-mobile.png"), animations: "disabled" })
    ai = false
    await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
    await page.reload()
    await page.locator(".gateway-card__main").filter({ hasText: gateway.name }).click()
    await expect(panel).toContainText("Aira 已关闭")
    await expect(panel.getByRole("button", { name: "用 Aira 审阅勘察报告" })).toHaveCount(0)
    await expect(panel.getByRole("button", { name: "让 Aira 推荐软件候选" })).toHaveCount(0)
    await panel.locator(".n-select").click()
    await selectVisibleOption(page, equipment.name)
    await expect(panel).toContainText("已结束或取消")
    await panel.getByRole("button", { name: "查看与审核", exact: true }).click()
    await expect(page.getByRole("dialog").last().getByRole("heading", { name: "分析已保存", exact: true })).toBeVisible()
    expect(attempts).toBe(1)
  })
}

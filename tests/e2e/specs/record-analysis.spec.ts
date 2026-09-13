import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

// No route mocks or model requests: scopes, previews, confirmation, statistics,
// charts and methods use the real API. AI_ENABLED=false also strictly verifies
// the disabled backend capability and hidden AI controls; default CI can keep AI on.
for (const { locale, chart } of [
  { locale: "en-US", chart: "bar" },
  { locale: "en-US", chart: "line" },
  { locale: "zh-CN", chart: "bar" },
  { locale: "zh-CN", chart: "line" },
] as const) {
  test(`AI-independent manual Record analysis computes real ${chart} data and preserves a reusable method (${locale})`, async ({ page }, testInfo) => {
    const fixtures = await loadFixtures()
    await page.addInitScript(language => localStorage.setItem("lang", JSON.stringify({ data: language, expire: null })), locale)
    const project = `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}`
    await page.goto(`${project}/protocols/${fixtures.analysis.protocol_uid}/records`)
    const contextResponse = page.waitForResponse(response => response.url().endsWith(`/protocols/${fixtures.analysis.protocol_id}/analysis-context`) && response.request().method() === "POST")
    await page.getByTestId("analysis-filtered-trigger").click()
    const loadedContext = await contextResponse
    expect(loadedContext.request().postDataJSON()).toMatchObject({ mode: "latest", filters: {} })
    const selectedContext = await loadedContext.json()
    if (process.env.AI_ENABLED === "false")
      expect(selectedContext.ai_available, "Explicit AI-off acceptance must use the real disabled backend capability").toBe(false)
    expect(selectedContext.protocol_versions).toEqual(["1.0.0"])
    expect(selectedContext.fields.find((field: { key: string }) => field.key === "measurement")).toMatchObject({ type: "number", unit: "mg/L" })
    await expect(page.getByTestId("analysis-workbench")).toBeVisible()
    if (selectedContext.ai_available === false)
      await expect(page.getByTestId("analysis-ai-draft-generate")).toHaveCount(0)
    await expect(page.getByTestId("analysis-selection-summary")).toContainText(locale === "en-US" ? "applied filters" : "已应用筛选条件")
    await page.getByTestId("analysis-numeric-fields").click()
    await selectVisibleOption(page, "Measurement")
    await page.keyboard.press("Escape")
    await page.getByTestId("analysis-chart-type").click()
    const chartLabel = locale === "en-US" ? chart === "bar" ? "Bar chart" : "Line chart" : chart === "bar" ? "柱状图" : "折线图"
    await selectVisibleOption(page, chartLabel)
    await page.getByTestId("analysis-question").locator("textarea").fill(`Synthetic mean ${locale} ${chart}`)
    const previewResponse = page.waitForResponse(response => response.url().endsWith("/analyses/preview") && response.request().method() === "POST")
    await page.getByTestId("analysis-preview").click()
    const preview = await (await previewResponse).json()
    expect(preview.recipe.chart).toBe(chart)
    expect(preview.ai_provenance).toEqual({})
    expect(preview.summary.counts).toEqual({ total: 12, included: 12, filtered_out: 0 })
    expect(preview.summary.field_stats.measurement).toEqual({ count: 12, missing: 0, invalid: 0 })
    await expect(page.getByTestId("analysis-preview-dialog")).toBeVisible()
    const confirmation = page.waitForResponse(response => response.url().endsWith("/analyses") && response.request().method() === "POST")
    const computedResponse = page.waitForResponse(async (response) => {
      if (response.request().method() !== "GET" || !/\/analyses\/[0-9a-f-]+$/.test(new URL(response.url()).pathname) || !response.ok())
        return false
      return (await response.json()).status === "succeeded"
    }, { timeout: 30_000 })
    await page.getByTestId("analysis-confirm").click()
    expect((await confirmation).ok()).toBe(true)
    const computed = await (await computedResponse).json()
    expect(computed.result.groups[0].fields.measurement).toMatchObject({ mean: 13, count: 12, missing: 0, invalid: 0 })
    expect(computed.result.chart).toMatchObject({ type: chart, statistic: "mean", series: [{ field: "measurement", unit: "mg/L", points: [{ group_index: 0, value: 13, count: 12 }] }] })
    const table = page.getByTestId("analysis-result-table")
    await expect(table).toBeVisible({ timeout: 30_000 })
    await expect(table.locator("tbody tr")).toHaveCount(1)
    await expect(table.locator("tbody tr td").nth(1)).toHaveText("12")
    await expect(table.locator("tbody tr td").nth(4)).toHaveText("13")
    const figure = page.getByTestId("analysis-result-charts").locator(`figure[data-field="measurement"][data-chart-type="${chart}"]`)
    await expect(figure).toBeVisible()
    const point = figure.locator("g[data-group-index='0']")
    await expect(point).toHaveAttribute("data-mean", "13")
    await expect(point).toHaveAttribute("data-count", "12")
    await expect(point.locator(chart === "bar" ? ".analysis-chart-bar" : ".analysis-chart-point")).toBeVisible()
    await expect(figure.locator("figcaption")).toContainText("mg/L")
    if (selectedContext.ai_available === false)
      await expect(page.getByTestId("analysis-ai-interpretation-generate")).toHaveCount(0)
    await page.reload()
    await expect(table.locator("tbody tr td").nth(4)).toHaveText("13")
    await expect(point).toHaveAttribute("data-mean", "13")
    await page.getByTestId("analysis-save-pipeline").click()
    const methodTitle = `Synthetic method ${locale} ${chart} ${Date.now()}`
    await page.getByTestId("analysis-method-title").locator("input").fill(methodTitle)
    await page.getByTestId("analysis-confirm-save-method").click()
    await expect(page.getByTestId("analysis-pipeline-item").filter({ hasText: methodTitle })).toBeVisible()
    await expect(page.getByTestId("analysis-method-title")).toBeHidden()
    await page.setViewportSize({ width: 390, height: 844 })
    for (const scrollArea of [figure.locator(".analysis-chart-scroll"), table.locator("..")]) {
      await expect(scrollArea).toHaveCSS("overflow-x", "auto")
      expect(await scrollArea.evaluate(element => element.scrollWidth > element.clientWidth)).toBe(true)
      await scrollArea.focus()
      await page.keyboard.press("ArrowRight")
      await expect.poll(() => scrollArea.evaluate(element => element.scrollLeft)).toBeGreaterThan(0)
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    await page.getByTestId("analysis-save-pipeline").click()
    const saveDialog = page.locator(".n-modal").filter({ has: page.getByTestId("analysis-method-title") })
    await expect(saveDialog).toBeVisible()
    await expect.poll(async () => (await saveDialog.boundingBox())?.width).toBeLessThanOrEqual(358)
    const box = (await saveDialog.boundingBox())!
    expect(box.x).toBeGreaterThanOrEqual(15)
    expect(box.x + box.width).toBeLessThanOrEqual(375)
    await expect(page.getByTestId("analysis-confirm-save-method")).toBeInViewport({ ratio: 1 })
    await page.keyboard.press("Escape")
    await expect(page.getByTestId("analysis-method-title")).toBeHidden()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`analysis-${chart}-phone.png`), fullPage: true })
  })
}

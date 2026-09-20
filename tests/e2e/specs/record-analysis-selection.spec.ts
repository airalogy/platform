import type { Page, Response } from "@playwright/test"
import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

interface SourceRecord {
  record_id: string
  record_version: number
  metadata: { record_num: number }
  data: { var: { measurement: number } }
}

// Real Record table, pagination, selection handoff, API and persistent worker.
// No route mocks, generated results or synthetic browser-side selector state.
function recordsResponse(page: Page, protocolId: string, predicate: (url: URL) => boolean) {
  return page.waitForResponse(response => response.request().method() === "GET"
    && new URL(response.url()).pathname.endsWith(`/protocols/${protocolId}/records`)
    && predicate(new URL(response.url())))
}

async function sourceRows(response: Response): Promise<SourceRecord[]> {
  expect(response.ok(), await response.text()).toBe(true)
  return (await response.json()).records
}

function references(records: SourceRecord[]) {
  return records.map(record => ({ id: record.record_id, version: record.record_version }))
    .sort((left, right) => left.id.localeCompare(right.id))
}

async function computeSelection(page: Page, expected: SourceRecord[], locale: "en-US" | "zh-CN") {
  await expect(page.getByTestId("analysis-workbench")).toBeVisible()
  await page.getByTestId("analysis-numeric-fields").click()
  await selectVisibleOption(page, "Measurement")
  await page.keyboard.press("Escape")
  await page.getByTestId("analysis-chart-type").click()
  await selectVisibleOption(page, locale === "en-US" ? "Bar chart" : "柱状图")
  await page.getByTestId("analysis-question").locator("textarea").fill("Verify exact user-selected synthetic measurements")
  const previewResponse = page.waitForResponse(response => response.url().endsWith("/analyses/preview") && response.request().method() === "POST")
  await page.getByTestId("analysis-preview").click()
  const previewHttp = await previewResponse
  expect(previewHttp.ok(), await previewHttp.text()).toBe(true)
  const preview = await previewHttp.json()
  expect(preview.recipe.chart).toBe("bar")
  expect(preview.summary.counts).toEqual({ total: expected.length, included: expected.length, filtered_out: 0 })
  expect(references(preview.summary.sources)).toEqual(references(expected))
  expect(preview.summary.field_stats.measurement).toEqual({ count: expected.length, missing: 0, invalid: 0 })
  await expect(page.getByTestId("analysis-preview-dialog")).toBeVisible()

  const completed = page.waitForResponse(async (response) => {
    if (response.request().method() !== "GET" || !/\/analyses\/[0-9a-f-]+$/.test(new URL(response.url()).pathname) || !response.ok())
      return false
    return (await response.json()).status === "succeeded"
  }, { timeout: 30_000 })
  const confirmed = page.waitForResponse(response => response.url().endsWith("/analyses") && response.request().method() === "POST")
  await page.getByTestId("analysis-confirm").click()
  const confirmation = await confirmed
  expect(confirmation.ok(), await confirmation.text()).toBe(true)
  const report = await (await completed).json()
  expect(references(report.source_snapshot.records)).toEqual(references(expected))
  const mean = expected.reduce((total, row) => total + row.data.var.measurement, 0) / expected.length
  expect(report.result.groups[0].fields.measurement).toMatchObject({ count: expected.length, mean, missing: 0, invalid: 0 })
  expect(report.result.chart).toMatchObject({ type: "bar", statistic: "mean", series: [{ field: "measurement", unit: "mg/L", points: [{ group_index: 0, count: expected.length, value: mean }] }] })
  expect(report.source_selection).toEqual(preview.source_selection)
  const table = page.getByTestId("analysis-result-table")
  await expect(table).toBeVisible()
  await expect(table.locator("tbody tr td").nth(1)).toHaveText(String(expected.length))
  await expect(table.locator("tbody tr td").nth(4)).toHaveText(String(mean))
  const figure = page.getByTestId("analysis-result-charts").locator('figure[data-field="measurement"][data-chart-type="bar"]')
  const point = figure.locator("g[data-group-index='0']")
  await expect(figure).toBeVisible()
  await expect(point).toHaveAttribute("data-count", String(expected.length))
  await expect(point).toHaveAttribute("data-mean", String(mean))
  await expect(point.locator(".analysis-chart-bar")).toBeVisible()
  await page.reload()
  await expect(table.locator("tbody tr td").nth(1)).toHaveText(String(expected.length))
  await expect(table.locator("tbody tr td").nth(4)).toHaveText(String(mean))
  await expect(point).toHaveAttribute("data-count", String(expected.length))
  await expect(point).toHaveAttribute("data-mean", String(mean))
  await expect(point.locator(".analysis-chart-bar")).toBeVisible()
  return report
}

for (const locale of ["en-US", "zh-CN"] as const) {
  const labels = locale === "en-US"
    ? { advanced: "Advanced search", number: "Enter record number", apply: "Apply filters" }
    : { advanced: "高级搜索", number: "输入记录编号", apply: "应用筛选" }

  test(`Cross-page selected Record revisions survive unapplied filter edits and compute only those sources (${locale})`, async ({ page }) => {
    test.setTimeout(90_000)
    const fixtures = await loadFixtures()
    const protocolId = fixtures.analysis.protocol_id
    await page.addInitScript((language) => {
      localStorage.setItem("lang", JSON.stringify({ data: language, expire: null }))
      // Only restore the real table's default page-size preference, not its
      // selection state. The twelve immutable fixture rows then span two pages.
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith("airalogy:record-view:") && key.endsWith(":page-size"))
          localStorage.removeItem(key)
      }
    }, locale)
    const firstResponse = recordsResponse(page, protocolId, url => url.searchParams.get("page_size") === "10" && url.searchParams.get("page") === "1")
    await page.goto(`/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/protocols/${fixtures.analysis.protocol_uid}/records`)
    const firstPage = await sourceRows(await firstResponse)
    expect(firstPage).toHaveLength(10)
    const rows = page.locator(".aimd-record-table-view tbody tr")
    await expect(rows).toHaveCount(10)
    await expect(rows.first().locator(".aimd-record-table-view__record-link")).toHaveText(`#${firstPage[0].metadata.record_num}`)
    await rows.first().getByRole("checkbox").check()
    await expect(page.getByTestId("analysis-selected-trigger")).toContainText("1")

    const secondResponse = recordsResponse(page, protocolId, url => url.searchParams.get("page") === "2" && url.searchParams.get("page_size") === "10")
    await page.locator(".n-pagination .n-pagination-item").filter({ hasText: /^2$/ }).click()
    const secondPage = await sourceRows(await secondResponse)
    expect(secondPage).toHaveLength(2)
    await expect(rows).toHaveCount(2)
    await expect(rows.first().locator(".aimd-record-table-view__record-link")).toHaveText(`#${secondPage[0].metadata.record_num}`)
    await rows.first().getByRole("checkbox").check()
    await expect(page.getByTestId("analysis-selected-trigger")).toContainText("2")
    const selected = [firstPage[0], secondPage[0]]
    expect(selected[0].record_id).not.toBe(selected[1].record_id)

    await page.getByRole("button", { name: labels.advanced, exact: true }).click()
    await page.getByPlaceholder(labels.number, { exact: true }).fill("999999")
    const selectedContext = page.waitForResponse(response => response.url().endsWith(`/protocols/${protocolId}/analysis-context`) && response.request().method() === "POST")
    await page.getByTestId("analysis-selected-trigger").click()
    const context = await selectedContext
    expect(context.ok(), await context.text()).toBe(true)
    const selection = context.request().postDataJSON()
    expect(selection.mode).toBe("selected")
    expect(selection.filters).toEqual({})
    expect(selection.records.slice().sort((left: { id: string }, right: { id: string }) => left.id.localeCompare(right.id))).toEqual(references(selected))
    const report = await computeSelection(page, selected, locale)
    expect(report.source_snapshot.records).toHaveLength(2)
    expect(report.source_snapshot.records.some((row: { record_id: string }) => row.record_id === firstPage[1].record_id)).toBe(false)
    expect(report.source_snapshot.records.some((row: { record_id: string }) => row.record_id === secondPage[1].record_id)).toBe(false)
  })

  test(`Applied Record filters, not pending editor text, determine actual analysis and persisted result (${locale})`, async ({ page }) => {
    test.setTimeout(90_000)
    const fixtures = await loadFixtures()
    const protocolId = fixtures.analysis.protocol_id
    await page.addInitScript(language => localStorage.setItem("lang", JSON.stringify({ data: language, expire: null })), locale)
    await page.goto(`/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/protocols/${fixtures.analysis.protocol_uid}/records`)
    await page.getByRole("button", { name: labels.advanced, exact: true }).click()
    const number = page.getByPlaceholder(labels.number, { exact: true })
    await number.fill("1")
    const appliedResponse = recordsResponse(page, protocolId, url => url.searchParams.get("number") === "1")
    await page.getByRole("button", { name: labels.apply, exact: true }).click()
    const appliedRows = await sourceRows(await appliedResponse)
    expect(appliedRows).toHaveLength(1)
    expect(appliedRows[0].metadata.record_num).toBe(1)
    await expect(page.getByTestId("analysis-filtered-trigger")).toBeEnabled()
    await number.fill("2")
    const contextResponse = page.waitForResponse(response => response.url().endsWith(`/protocols/${protocolId}/analysis-context`) && response.request().method() === "POST")
    await page.getByTestId("analysis-filtered-trigger").click()
    const context = await contextResponse
    expect(context.ok(), await context.text()).toBe(true)
    expect(context.request().postDataJSON()).toEqual({ mode: "latest", filters: { number: 1 } })
    const report = await computeSelection(page, appliedRows, locale)
    expect(report.source_selection).toMatchObject({ mode: "latest", filters: { number: 1 } })
  })
}

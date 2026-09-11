import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

for (const locale of ["en-US", "zh-CN"]) {
  test(`native Record column actions retain preferences and fit narrow screens (${locale})`, async ({ page }, testInfo) => {
    const fixtures = await loadFixtures()
    await page.addInitScript(language => localStorage.setItem("lang", JSON.stringify({ data: language, expire: null })), locale)
    // Keep real authentication, permissions and Records. Only the displayed
    // Protocol catalogue is expanded with synthetic fields to exercise >6 columns.
    await page.route("**/api/protocols/by_uid?**", async (route) => {
      const response = await route.fetch()
      const body = await response.json()
      const protocol = body.data || body
      protocol.aimd = [
        ...Array.from({ length: 10 }, (_, index) => `{{var|synthetic_${index}: str}}`),
        "{{step|prepare}} Prepare synthetic sample.",
        "{{check|quality}} Check synthetic quality.",
        "{{var_table|measurements, subvars=[var(concentration: float), var(signal: float)]}}",
      ].join("\n\n")
      await route.fulfill({ response, json: body })
    })
    const path = `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/protocols/${fixtures.schema_governance.protocol_uid}/records`
    await page.goto(path)
    const table = page.locator(".aimd-record-table-view")
    const picker = table.locator(".aimd-record-table-view__field-picker")
    const fieldHeaders = table.locator("thead [data-field-key]")
    const metadataHeaders = table.locator("thead [data-metadata-column-key]")
    await expect(fieldHeaders).toHaveCount(6)
    await picker.locator("summary").click()
    const all = picker.getByRole("button", { name: locale === "en-US" ? "Show all columns" : "显示全部列", exact: true })
    const reset = picker.getByRole("button", { name: locale === "en-US" ? "Restore default columns" : "恢复默认列", exact: true })
    const fieldCount = await picker.locator("input[data-field-key]").count()
    expect(fieldCount).toBeGreaterThan(12)
    const metadata = picker.locator("input[data-metadata-column-key]")
    for (const option of await metadata.all())
      await option.uncheck()
    await expect(metadataHeaders).toHaveCount(0)
    await all.focus()
    await page.keyboard.press("Enter")
    await expect(fieldHeaders).toHaveCount(fieldCount)
    await expect(metadataHeaders).toHaveCount(3)
    await expect(all).toBeDisabled()
    await page.reload()
    await expect(fieldHeaders).toHaveCount(fieldCount)
    await expect(metadataHeaders).toHaveCount(3)
    await page.setViewportSize({ width: 390, height: 844 })
    await picker.locator("summary").click()
    await all.scrollIntoViewIfNeeded()
    const menuBox = (await picker.locator(".aimd-record-table-view__field-menu").boundingBox())!
    expect(menuBox.x).toBeGreaterThanOrEqual(0)
    expect(menuBox.x + menuBox.width).toBeLessThanOrEqual(391)
    const scroller = table.locator(".aimd-record-table-view__scroller")
    expect(await scroller.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true)
    await scroller.evaluate(el => el.scrollLeft = el.scrollWidth)
    expect(await scroller.evaluate(el => el.scrollLeft)).toBeGreaterThan(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath("record-columns-phone.png") })
    await picker.locator("input[data-field-key]").first().uncheck()
    await expect(all).toBeEnabled()
    await reset.focus()
    await page.keyboard.press("Enter")
    await expect(fieldHeaders).toHaveCount(6)
    await expect(metadataHeaders).toHaveCount(3)
    await expect(reset).toBeDisabled()
    await page.reload()
    await expect(fieldHeaders).toHaveCount(6)
    await expect(metadataHeaders).toHaveCount(3)
  })
}

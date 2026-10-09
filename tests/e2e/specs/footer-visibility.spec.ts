import type { Locator } from "@playwright/test"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

async function expectConfiguredCompliance(footer: Locator) {
  if (process.env.VITE_CHINA_COMPLIANCE_FOOTER !== "Y")
    return
  if (process.env.VITE_ICP_RECORD_NUMBER) {
    await expect(footer.getByRole("link", { name: process.env.VITE_ICP_RECORD_NUMBER, exact: true }))
      .toHaveAttribute("href", process.env.VITE_ICP_RECORD_URL || "https://beian.miit.gov.cn/")
  }
  if (process.env.VITE_POLICE_RECORD_NUMBER)
    await expect(footer).toContainText(process.env.VITE_POLICE_RECORD_NUMBER)
}

for (const width of [390, 1440]) {
  test(`cached hidden footer cannot hide company information at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    await page.addInitScript(() => {
      localStorage.setItem("themeSettings", JSON.stringify({ data: { footer: { visible: false, fixed: false, height: 400, right: true } }, expire: null }))
      localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null }))
    })
    for (const path of ["/home", "/protocols/my"]) {
      await page.goto(path)
      const footer = page.getByRole("contentinfo")
      await expect(footer).toBeVisible()
      await expect(footer).toContainText("杭州渊楠科技有限公司 版权所有")
      await expectConfiguredCompliance(footer)
      await footer.scrollIntoViewIfNeeded()
      await expect(footer).toBeInViewport()
      const box = await footer.boundingBox()
      expect(box!.width).toBeLessThanOrEqual(width)
      await page.screenshot({ path: testInfo.outputPath(`${path === "/home" ? "home" : "protocols"}-footer.png`) })
      await page.reload()
      await expect(page.getByRole("contentinfo")).toContainText("杭州渊楠科技有限公司 版权所有")
    }
  })
}

test("leaving a Record report restores the footer without a page reload", async ({ page }) => {
  const fixtures = await loadFixtures()
  const record = fixtures.schema_governance
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
  await page.goto(`/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/protocols/${record.protocol_uid}/v${record.source_version}/record/${record.record_id}/v${record.record_version}`)
  await expect(page.getByRole("button", { name: "Revise", exact: true })).toBeVisible()
  await expect(page.getByRole("contentinfo")).toHaveCount(0)
  await page.getByRole("link", { name: "Log", exact: true }).click()
  await expect(page.getByRole("contentinfo")).toContainText("Hangzhou Airalogy Technology Co., Ltd.")
})

test.describe("anonymous landing page", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("company and configured compliance footer survive stale theme storage", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.addInitScript(() => {
      localStorage.setItem("themeSettings", JSON.stringify({ data: { footer: { visible: false } }, expire: null }))
      localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null }))
    })
    await page.goto("/")
    const footer = page.getByRole("contentinfo")
    await expect(footer).toContainText("Hangzhou Airalogy Technology Co., Ltd.")
    await expectConfiguredCompliance(footer)
    await footer.scrollIntoViewIfNeeded()
    await expect(footer).toBeInViewport()
    await page.screenshot({ path: testInfo.outputPath("landing-footer.png") })
  })
})

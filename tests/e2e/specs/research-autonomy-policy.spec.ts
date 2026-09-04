import { expect, test } from "@playwright/test"

test("Lab owner versions bounded Research autonomy policy", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null }))
  })
  await page.goto("/labs/dev_lab/projects/quickstart/research")
  await page.getByTestId("research-policy-open").click()

  await expect(page.getByText("辅助执行始终询问", { exact: true })).toBeVisible()
  const bounded = page.getByTestId("research-policy-bounded_autopilot")
  const switches = bounded.getByRole("switch")
  await expect(switches).toHaveCount(3)
  await expect(switches.nth(0)).toBeChecked()
  await expect(switches.nth(1)).not.toBeChecked()
  await switches.nth(1).click()

  await page.getByTestId("research-policy-reason").locator("textarea").fill(
    "端到端测试：允许创建不触发外部操作的被动等待。",
  )
  await page.getByTestId("research-policy-preview").click()
  await expect(page.getByText("确认后会为未来 Research Environment", { exact: false })).toBeVisible()
  await page.getByTestId("research-policy-confirm").click()

  await expect(page.getByText("Lab 策略", { exact: true })).toBeVisible()
  await expect(page.getByText("第 1 版", { exact: false })).toBeVisible()
  await expect(bounded.getByRole("switch").nth(1)).toBeChecked()
})

import type { Locator, Page } from "@playwright/test"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

test.beforeEach(async ({ page }, testInfo) => {
  await page.addInitScript((language) => {
    localStorage.setItem("lang", JSON.stringify({ data: language, expire: null }))
  }, testInfo.title.startsWith("Chinese") ? "zh-CN" : "en-US")
})

async function assertDialogFits(page: Page, dialog: Locator, maxWidth: number) {
  await expect(dialog).toBeVisible()
  const viewport = page.viewportSize()!
  // Wait for the modal's entrance scale transition before measuring layout.
  await expect.poll(async () => (await dialog.boundingBox())?.width).toBeCloseTo(Math.min(maxWidth, viewport.width - 32), 0)
  const box = await dialog.boundingBox()
  expect(box!.width).toBeLessThanOrEqual(maxWidth + 1)
  expect(box!.x).toBeGreaterThanOrEqual(15)
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width - 15)
  expect(box!.y).toBeGreaterThanOrEqual(0)
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height + 1)
  await expect(dialog.locator(".n-card__footer")).toBeInViewport()
}

test("core navigation is discoverable, keyboard operable and bounded at every breakpoint", async ({ page }) => {
  for (const width of [360, 390, 850, 1280, 1536]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto("/knowledge")
    const header = page.getByTestId("app-shell-header")
    await expect(header).toBeVisible()
    const overflow = await header.evaluate((el) => {
      const bounds = el.getBoundingClientRect()
      return Array.from(el.children).filter(child => child.getBoundingClientRect().width > 0).some((child) => {
        const box = child.getBoundingClientRect()
        return box.right > bounds.right + 1 || box.left < bounds.left - 1
      })
    })
    expect(overflow, `header overflow at ${width}px`).toBe(false)
    if (width < 640)
      await expect(page.getByTestId("app-shell-content")).toHaveCSS("padding-left", "16px")
    if (width < 1280) {
      const trigger = page.getByTestId("workspace-menu-trigger")
      await expect(trigger).toHaveText(/Knowledge/)
      await trigger.focus()
      await page.keyboard.press("Enter")
    }
    const log = page.getByRole("link", { name: "Log", exact: true })
    await expect(log).toBeVisible()
    await log.focus()
    await page.keyboard.press("Enter")
    await expect(page).toHaveURL(/\/users\/[^/]+\/records/)
    if (width < 1280)
      await expect(page.getByTestId("workspace-menu-trigger")).toHaveText(/Log/)
    else
      await expect(page.getByRole("link", { name: "Log", exact: true })).toHaveAttribute("aria-current", "page")
    await expect(page.getByRole("heading", { name: "My Log", exact: true })).toBeVisible()
  }
})

test("DOI input and confirmation footer fit phones, tablets and desktops", async ({ page }, testInfo) => {
  for (const width of [390, 850, 1440]) {
    await page.setViewportSize({ width, height: 844 })
    await page.goto("/knowledge")
    await page.getByRole("button", { name: "Import paper", exact: true }).first().click()
    const dialog = page.getByRole("dialog")
    await assertDialogFits(page, dialog, 800)
    const source = page.getByTestId("paper-import-source").locator("input")
    expect((await source.boundingBox())!.width).toBeGreaterThan(220)
    await source.fill("10.1234/synthetic-ui-check")
    await expect(page.getByTestId("paper-metadata")).not.toHaveAttribute("open")
    await page.getByTestId("paper-metadata").locator("summary").click()
    await assertDialogFits(page, dialog, 800)
    await expect(source).toHaveValue("10.1234/synthetic-ui-check")
    if (width === 390 || width === 1440)
      await page.screenshot({ path: testInfo.outputPath(`paper-dialog-${width}.png`) })
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click()
  }
})

test("DOI fallback preserves input and failed confirmation retains its preview", async ({ page }) => {
  await page.goto("/knowledge")
  await page.getByRole("button", { name: "Import paper", exact: true }).first().click()
  const dialog = page.getByRole("dialog").filter({ has: page.getByTestId("paper-destination") })
  const source = page.getByTestId("paper-import-source").locator("input")
  const doi = `10.1234/synthetic-ui-${Date.now()}`
  const title = `Synthetic UI paper ${Date.now()}`
  await source.fill(doi)
  // Simulate the provider boundary; the subsequent preview and saved import use the real API.
  await page.route("**/api/knowledge/papers/import/preview", route => route.fulfill({
    status: 422,
    contentType: "application/json",
    body: JSON.stringify({ detail: "DOI import requires metadata when no LiteratureProvider is configured" }),
  }))
  await dialog.getByRole("button", { name: "Preview import", exact: true }).click()
  await expect(page.getByTestId("paper-import-error")).toContainText("Enter the paper title")
  await expect(source).toHaveValue(doi)
  await expect(page.getByTestId("paper-metadata")).toHaveAttribute("open")
  await page.unroute("**/api/knowledge/papers/import/preview")
  await dialog.getByPlaceholder("Enter the published title").fill(title)
  await dialog.getByRole("button", { name: "Preview import", exact: true }).click()
  await expect(dialog).toContainText(title)
  await expect(dialog).toContainText("My Knowledge")
  await expect(dialog).toContainText("Only me")
  await page.route("**/api/knowledge/papers/import/*/confirm", route => route.abort("failed"))
  await dialog.getByRole("button", { name: "Confirm import", exact: true }).click()
  await expect(page.getByTestId("paper-import-error")).toContainText("check the saved items")
  await expect(dialog).toContainText(title)
  await page.unroute("**/api/knowledge/papers/import/*/confirm")
  await dialog.getByRole("button", { name: "Confirm import", exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible()
})

test("manual Task errors preserve the form and narrow-screen footer remains visible", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto("/research/tasks")
  await page.getByRole("button", { name: "New Research Task", exact: true }).first().click()
  const dialog = page.getByRole("dialog")
  await assertDialogFits(page, dialog, 768)
  await page.getByTestId("research-task-title").locator("input").fill("Synthetic usability Task")
  await page.getByTestId("research-task-goal").locator("textarea").fill("Check the interface with synthetic observations.")
  await page.getByTestId("research-task-success-criteria").locator("textarea").fill("The result can be traced to its saved Task.")
  await page.route("**/api/research-tasks/preview", route => route.abort("failed"))
  await dialog.getByRole("button", { name: "Preview Task", exact: true }).click()
  await expect(page.getByTestId("research-task-save-error")).toBeVisible()
  await expect(page.getByTestId("research-task-title").locator("input")).toHaveValue("Synthetic usability Task")
  await page.unroute("**/api/research-tasks/preview")
  await dialog.getByRole("button", { name: "Preview Task", exact: true }).click()
  await expect(dialog.getByRole("button", { name: "Confirm and create", exact: true })).toBeVisible()
  await assertDialogFits(page, dialog, 768)
  await dialog.getByRole("button", { name: "Confirm and create", exact: true }).click()
  await expect(page.getByTestId("research-next-step")).toContainText("start the Task")
  await expect(page.getByTestId("research-environment-details")).not.toHaveAttribute("open")
  await page.screenshot({ path: testInfo.outputPath("research-task-phone.png"), fullPage: true })
})

test("home uses a compact truthful empty state and a single primary Record action", async ({ page }) => {
  // Pin a genuinely empty response shape so this visual contract is independent of other journeys.
  for (const [endpoint, key] of [["research-tasks", "tasks"], ["research-work-items", "work_items"], ["research-approvals", "approvals"]]) {
    await page.route(`**/api/${endpoint}?*`, route => route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ [key]: [], total_count: 0 }),
    }))
  }
  await page.goto("/home")
  await expect(page.getByTestId("workbench-loading")).toHaveCount(0)
  await expect(page.getByTestId("workbench-clear")).toBeVisible()
  await expect(page.getByTestId("workbench-attention")).toHaveCount(0)
  await expect(page.getByTestId("task-workbench").getByRole("button", { name: "Start a Record", exact: true })).toHaveCount(1)
})

test("Chinese navigation and paper dialogs remain readable on small screens", async ({ page }, testInfo) => {
  for (const width of [390, 850, 1440]) {
    await page.setViewportSize({ width, height: 844 })
    await page.goto("/knowledge")
    await expect(page.getByRole("heading", { name: "我的知识", exact: true })).toBeVisible()
    if (width < 1280)
      await page.getByTestId("workspace-menu-trigger").click()
    const knowledgeLink = page.getByRole("link", { name: "知识", exact: true })
    await expect(knowledgeLink).toHaveAttribute("aria-current", "page")
    await knowledgeLink.click()
    await expect(page.getByText("文献库", { exact: true })).toBeVisible()
    await expect(page.getByText("知识条目", { exact: true })).toBeVisible()
    await page.getByRole("button", { name: "新建知识条目", exact: true }).first().click()
    const knowledgeDialog = page.getByRole("dialog")
    await assertDialogFits(page, knowledgeDialog, 768)
    await expect(knowledgeDialog).toContainText("我的知识")
    await expect(knowledgeDialog).toContainText("知识类型")
    await expect(knowledgeDialog).toContainText("知识内容")
    await expect(knowledgeDialog.getByRole("button", { name: "创建知识条目", exact: true })).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath(`knowledge-editor-zh-${width}.png`) })
    await knowledgeDialog.getByRole("button", { name: "取消", exact: true }).click()
    await page.getByRole("button", { name: "导入文献", exact: true }).first().click()
    const dialog = page.getByRole("dialog")
    await assertDialogFits(page, dialog, 800)
    await expect(page.getByTestId("paper-destination")).toContainText("我的知识")
    expect((await page.getByTestId("paper-import-source").locator("input").boundingBox())!.width).toBeGreaterThan(220)
    await page.screenshot({ path: testInfo.outputPath(`knowledge-zh-${width}.png`) })
    await dialog.getByRole("button", { name: "取消", exact: true }).click()
    if (width < 1280)
      await page.getByTestId("workspace-menu-trigger").click()
    await page.getByRole("link", { name: "日志", exact: true }).click()
    await expect(page.getByRole("heading", { name: "我的日志", exact: true })).toBeVisible()
    await page.getByRole("button", { name: "新建日志", exact: true }).click()
    const logDialog = page.getByRole("dialog")
    await expect(logDialog.getByRole("textbox").first()).toHaveValue("我的日志")
    await expect(logDialog.getByRole("button", { name: "预览日志", exact: true })).toBeVisible()
    await logDialog.getByRole("button", { name: "取消", exact: true }).click()
  }
})

test("Chinese Log page titles identify the Lab and Project scope", async ({ page }) => {
  const fixtures = await loadFixtures()
  await page.goto(`/labs/${fixtures.lab.uid}/records`)
  await expect(page.getByRole("heading", { name: "实验室日志", exact: true })).toBeVisible()
  await page.goto(`/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/records`)
  await expect(page.getByRole("heading", { name: "项目日志", exact: true })).toBeVisible()
})

test("Log save failure keeps the preview and reports an uncertain confirmation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto("/home")
  await page.getByTestId("workspace-menu-trigger").click()
  await page.getByRole("link", { name: "Log", exact: true }).click()
  await page.getByRole("button", { name: "New Log entry", exact: true }).click()
  const dialog = page.getByRole("dialog")
  await assertDialogFits(page, dialog, 832)
  await dialog.getByRole("textbox").nth(1).fill("Synthetic unsaved progress")
  await dialog.getByRole("textbox").nth(2).fill("Keep this text if the connection fails.")
  await dialog.getByRole("button", { name: "Preview entry", exact: true }).click()
  await page.route("**/api/research-log/entries", route => route.abort("failed"))
  await dialog.getByRole("button", { name: "Confirm and save", exact: true }).click()
  await expect(page.getByTestId("log-save-error")).toContainText("check the saved items")
  await expect(page.getByTestId("log-save-error")).toBeInViewport()
  await expect(dialog).toContainText("Keep this text if the connection fails.")
})

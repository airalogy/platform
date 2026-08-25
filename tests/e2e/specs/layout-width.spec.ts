import type { Page } from "@playwright/test"
import { expect, test } from "@playwright/test"

async function getShellWidths(page: Page) {
  const header = page.getByTestId("app-shell-header")
  const content = page.getByTestId("app-shell-content")
  await expect(header).toBeVisible()
  await expect(content).toBeVisible()

  const [headerBox, contentBox] = await Promise.all([
    header.boundingBox(),
    content.boundingBox(),
  ])
  expect(headerBox).not.toBeNull()
  expect(contentBox).not.toBeNull()

  return {
    header: Math.round(headerBox!.width),
    content: Math.round(contentBox!.width),
  }
}

test("workspace pages share the same wide application shell", async ({ page }) => {
  await page.setViewportSize({ width: 2000, height: 1000 })

  await page.goto("/home")
  const home = await getShellWidths(page)

  await page.goto("/protocols/my")
  const protocols = await getShellWidths(page)

  expect(protocols).toEqual(home)
  expect(protocols.header).toBeGreaterThan(1536)
  expect(protocols.content).toBeGreaterThan(1536)
})

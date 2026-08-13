import { expect, test } from "@playwright/test"

test("my protocols shows each Protocol's Lab and Project", async ({ page }) => {
  await page.goto("/protocols/my")

  const ownershipPaths = page.getByTestId("protocol-ownership-path")
  await expect(ownershipPaths.first()).toBeVisible()
  await expect(ownershipPaths.first()).toContainText("Dev Demo Lab")
  await expect(ownershipPaths.first()).toContainText("Quickstart Protocol Testing")

  const links = ownershipPaths.first().getByRole("link")
  await expect(links.nth(0)).toHaveAttribute("href", "/labs/dev_lab/projects")
  await expect(links.nth(1)).toHaveAttribute(
    "href",
    "/labs/dev_lab/projects/quickstart/protocols",
  )
})

import { mkdir } from "node:fs/promises"
import { expect, test as setup } from "@playwright/test"

const accounts = [
  {
    key: "owner",
    email: "dev.owner@airalogy.dev",
    password: "AiralogyDev123!",
  },
  {
    key: "viewer",
    email: "dev.viewer@airalogy.dev",
    password: "AiralogyDev123!",
  },
] as const

for (const account of accounts) {
  setup(`authenticate ${account.key}`, async ({ page }) => {
    await page.goto("/login")
    await page.getByTestId("login-email").locator("input").fill(account.email)
    await page.getByTestId("login-password").locator("input").fill(account.password)
    await page.getByTestId("login-submit").click()
    await expect(page).not.toHaveURL(/\/login(?:\?|$)/)
    await mkdir("tests/e2e/.auth", { recursive: true })
    await page.context().storageState({
      path: `tests/e2e/.auth/${account.key}.json`,
    })
  })
}

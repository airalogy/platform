import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

async function useChineseLocale(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null }))
  })
}

async function mockSmsLoginCapability(
  page: import("@playwright/test").Page,
  enabled: boolean,
) {
  await page.route(/\/api\/instance(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      json: {
        deployment_mode: "community",
        single_lab: false,
        initialized: true,
        signup_mode: "open",
        bootstrap_token_required: false,
        site_url: "http://127.0.0.1:3100",
        lab_structure_mode: "flat",
        documentation_profile: "community",
        documentation_url: "/docs/",
        support_url: "",
        ai_enabled: false,
        sms_login_enabled: enabled,
        sms_signup_required: false,
        enabled_chat_models: [],
        lab: null,
      },
    })
  })
}

test("SMS-enabled instances show phone and email login with phone selected", async ({ page }) => {
  await useChineseLocale(page)
  await mockSmsLoginCapability(page, true)

  await page.goto("/login")

  const phoneTab = page.locator(".n-tabs-tab").filter({ hasText: "手机号验证码登录" })
  const emailTab = page.locator(".n-tabs-tab").filter({ hasText: "邮箱登录" })
  await expect(page.locator(".n-tabs")).toBeVisible()
  await expect(phoneTab).toBeVisible()
  await expect(emailTab).toBeVisible()
  await expect(page.getByText("手机号登录", { exact: true })).toBeVisible()
  await expect(page.getByTestId("login-email")).not.toBeVisible()

  await emailTab.click()
  await expect(page.getByTestId("login-email")).toBeVisible()
})

test("SMS-disabled instances show only email login", async ({ page }) => {
  await useChineseLocale(page)
  await mockSmsLoginCapability(page, false)

  await page.goto("/login")

  await expect(page.locator(".n-tabs")).toHaveCount(0)
  await expect(page.getByText("邮箱登录", { exact: true })).toBeVisible()
  await expect(page.getByTestId("login-email")).toBeVisible()
  await expect(page.getByText("手机号验证码登录", { exact: true })).toHaveCount(0)
  await expect(page.getByText("手机号登录", { exact: true })).toHaveCount(0)
})

test("instance capability failures fall back to email login", async ({ page }) => {
  await useChineseLocale(page)
  await page.route(/\/api\/instance(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Instance status unavailable" }),
    })
  })

  await page.goto("/login")

  await expect(page.locator(".n-tabs")).toHaveCount(0)
  await expect(page.getByTestId("login-email")).toBeVisible()
})

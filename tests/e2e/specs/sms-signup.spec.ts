import { expect, test } from "@playwright/test"

test.use({ storageState: { cookies: [], origins: [] } })

async function useChineseLocale(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null }))
  })
}

async function mockInstance(
  page: import("@playwright/test").Page,
  smsSignupRequired: boolean,
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
        sms_login_enabled: false,
        sms_signup_required: smsSignupRequired,
        enabled_chat_models: [],
        lab: null,
      },
    })
  })
}

test("SMS-signup-required instances verify phone before account details", async ({ page }) => {
  await useChineseLocale(page)
  await mockInstance(page, true)
  await page.route(/\/api\/send_verify_code(?:\?.*)?$/, async (route) => {
    expect(route.request().postDataJSON()).toMatchObject({
      type: "signup",
      country_code: "86",
      phone: "13800138000",
    })
    await route.fulfill({ json: { success: true } })
  })
  await page.route(/\/api\/signup\/verify_phone(?:\?.*)?$/, async (route) => {
    expect(route.request().postDataJSON()).toMatchObject({
      country_code: "86",
      phone: "13800138000",
      verify_code: "123456",
    })
    await route.fulfill({
      json: {
        signup_verification_token: "verified-signup-token-12345678901234567890",
        expires_in: 1800,
      },
    })
  })

  await page.goto("/sign-up")

  await expect(page.getByText("验证手机号", { exact: true })).toBeVisible()
  await expect(page.getByPlaceholder("请输入邮箱")).toHaveCount(0)
  await page.getByPlaceholder("请输入手机号").fill("13800138000")
  await page.getByRole("button", { name: "发送验证码" }).click()
  await page.locator(".pin-input-digit").first().pressSequentially("123456")
  await page.getByRole("button", { name: "验证并继续" }).click()

  await expect(page.getByText("手机号已验证：+86 13800138000")).toBeVisible()
  await expect(page.getByPlaceholder("请输入邮箱")).toBeVisible()
})

test("SMS-signup-disabled instances keep email registration", async ({ page }) => {
  await useChineseLocale(page)
  await mockInstance(page, false)

  await page.goto("/sign-up")

  await expect(page.getByPlaceholder("请输入邮箱")).toBeVisible()
  await expect(page.getByText("验证手机号", { exact: true })).toHaveCount(0)
})

test("instance capability failures fail closed instead of showing email registration", async ({ page }) => {
  await useChineseLocale(page)
  await page.route(/\/api\/instance(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Instance status unavailable" }),
    })
  })

  await page.goto("/sign-up")

  await expect(page.getByText("注册服务暂不可用", { exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "重新加载" })).toBeVisible()
  await expect(page.getByPlaceholder("请输入邮箱")).toHaveCount(0)
  await expect(page.getByText("验证手机号", { exact: true })).toHaveCount(0)
})

test("missing signup capability fails closed during mixed-version deployment", async ({ page }) => {
  await useChineseLocale(page)
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
        sms_login_enabled: false,
        enabled_chat_models: [],
        lab: null,
      },
    })
  })

  await page.goto("/sign-up")

  await expect(page.getByText("注册服务暂不可用", { exact: true })).toBeVisible()
  await expect(page.getByPlaceholder("请输入邮箱")).toHaveCount(0)
})

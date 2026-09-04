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

  await page
    .getByTestId("research-policy-reason")
    .locator("textarea")
    .fill("端到端测试：允许创建不触发外部操作的被动等待。")
  await page.getByTestId("research-policy-preview").click()
  await expect(
    page.getByText("确认后会为未来 Research Environment", { exact: false }),
  ).toBeVisible()
  await page.getByTestId("research-policy-confirm").click()

  await expect(page.getByText("Lab 策略", { exact: true })).toBeVisible()
  await expect(page.getByText("第 1 版", { exact: false })).toBeVisible()
  await expect(bounded.getByRole("switch").nth(1)).toBeChecked()
})

test("Lab owner grants and revokes one evaluated autonomy target", async ({ page }) => {
  const targetDigest = "a".repeat(64)
  const executorDigest = "b".repeat(64)
  const evaluationDigest = "c".repeat(64)
  const target = {
    schema: "airalogy.research-autonomy-target.v1",
    capability_key: "tool:literature.search",
    capability_version: "1",
    executor_type: "platform_tool",
    executor_ref: { type: "platform_worker", id: "literature.search" },
    executor_digest: executorDigest,
    target_digest: targetDigest,
  }
  const evaluation = {
    schema: "airalogy.research-autonomy-evaluation.v1",
    target,
    evaluated_at: "2026-09-05T00:00:00+00:00",
    criteria: {
      minimum_supervised_successes: 5,
      maximum_sample: 10,
      allowed_failures: 0,
    },
    sample: [],
    completed_count: 5,
    failure_count: 0,
    passed: true,
    evaluation_digest: evaluationDigest,
  }
  let grant: Record<string, unknown> | null = null

  await page.route("**/research-autonomy-policies/evaluations**", async (route) => {
    await route.fulfill({ json: { items: [evaluation] } })
  })
  await page.route("**/research-autonomy-policies/grants**", async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const method = request.method()
    if (path.endsWith("/grants") && method === "GET") {
      await route.fulfill({ json: { items: grant ? [grant] : [], can_manage: true } })
      return
    }
    if (path.endsWith("/grants/preview") && method === "POST") {
      await route.fulfill({
        json: {
          preview_digest: "d".repeat(64),
          command: { next_revision: grant ? 2 : 1 },
          destination: { lab_id: "dev-lab-id", lab_uid: "dev_lab", lab_name: "Development Lab" },
          current: grant,
          effects: ["Allow only this exact capability version and executor boundary"],
        },
      })
      return
    }
    if (path.endsWith("/grants") && method === "PUT") {
      const payload = request.postDataJSON()
      grant = {
        schema: "airalogy.research-autonomy-grant.v1",
        id: "11111111-1111-4111-8111-111111111111",
        lab_id: "dev-lab-id",
        target,
        revision: 1,
        enabled: true,
        allowed_levels: payload.allowed_levels,
        evaluation,
        valid_until: payload.valid_until,
        reason: payload.reason,
        created_by_user_id: "owner-id",
        updated_by_user_id: "owner-id",
        created_at: "2026-09-05T00:00:00+00:00",
        updated_at: "2026-09-05T00:00:00+00:00",
      }
      await route.fulfill({ json: grant })
      return
    }
    if (path.endsWith("/revoke/preview") && method === "POST") {
      await route.fulfill({
        json: {
          preview_digest: "e".repeat(64),
          command: { next_revision: 2 },
          current: grant,
          effects: ["Exclude this grant from newly captured Research Environments"],
        },
      })
      return
    }
    if (path.endsWith("/revoke") && method === "POST") {
      grant = { ...grant!, enabled: false, revision: 2 }
      await route.fulfill({ json: grant })
      return
    }
    await route.fallback()
  })

  await page.addInitScript(() => {
    window.localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null }))
  })
  await page.goto("/labs/dev_lab/projects/quickstart/research")
  await page.getByTestId("research-policy-open").click()

  await expect(page.getByTestId(`research-autonomy-evaluation-${targetDigest}`)).toBeVisible()
  await page.getByTestId(`research-autonomy-grant-open-${targetDigest}`).click()
  await page
    .getByTestId("research-autonomy-grant-reason")
    .locator("textarea")
    .fill("五次受监督执行均成功，允许在有边界的自动执行中使用。")
  await page.getByTestId("research-autonomy-grant-preview").click()
  await expect(
    page.getByText("确认只影响未来的 Research Environment", { exact: false }),
  ).toBeVisible()
  await page.getByTestId("research-autonomy-grant-confirm").click()

  await expect(page.getByTestId(`research-autonomy-grant-${targetDigest}`)).toBeVisible()
  await page.getByTestId(`research-autonomy-revoke-${targetDigest}`).click()
  await page
    .getByTestId("research-autonomy-grant-reason")
    .locator("textarea")
    .fill("执行环境即将升级，撤销当前版本授权。")
  await page.getByTestId("research-autonomy-grant-preview").click()
  await page.getByTestId("research-autonomy-grant-confirm").click()

  await expect(page.getByTestId(`research-autonomy-grant-${targetDigest}`)).toHaveCount(0)
  await expect(page.getByTestId(`research-autonomy-grant-open-${targetDigest}`)).toContainText(
    "复核 / 续期",
  )
})

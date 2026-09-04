import { expect, test } from "@playwright/test"

function useChinese(page: import("@playwright/test").Page) {
  return page.addInitScript(() => {
    window.localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null }))
  })
}

test("Aira turns a research question into an editable Task draft without creating it", async ({ page }) => {
  await useChinese(page)
  let draftRequests = 0
  await page.route("**/api/research-tasks/draft-with-aira", async (route) => {
    draftRequests += 1
    const request = route.request().postDataJSON() as {
      project_id: string
      research_question: string
      additional_constraints: string
      autonomy_level: string
    }
    expect(request.research_question).toBe("哪些条件能提高候选化合物的细胞响应？")
    expect(request.additional_constraints).toBe("不超过已批准的安全阈值。")
    expect(request.autonomy_level).toBe("assisted")
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        draft: {
          project_id: request.project_id,
          title: "评估候选化合物的细胞响应",
          goal: "确定在安全边界内是否存在可重现的细胞响应。",
          success_criteria: ["报告预先定义的效应量和不确定性"],
          stop_conditions: ["达到已批准的安全阈值"],
          autonomy_level: "assisted",
          protocol_ids: [],
          tool_keys: [],
          knowledge_ids: [],
          resource_type_ids: [],
          service_offering_ids: [],
          compute_environment_ids: [],
          ai_model: "e2e-model",
        },
        rationale: "该草稿把问题限定为可观察且可审核的目标。",
        assumptions: ["样本和对照可用"],
        warnings: ["执行前需确认安全阈值"],
        model: "e2e-model",
        boundary: "Editable draft only.",
      }),
    })
  })

  await page.goto("/research/tasks")
  await page.getByRole("button", { name: "新建科研任务", exact: true }).first().click()

  const aira = page.getByTestId("research-task-aira")
  await expect(aira).toBeVisible()
  await aira.getByTestId("research-task-aira-question").locator("textarea").fill(
    "哪些条件能提高候选化合物的细胞响应？",
  )
  await aira.getByTestId("research-task-aira-constraints").locator("textarea").fill(
    "不超过已批准的安全阈值。",
  )
  await aira.getByTestId("research-task-aira-generate").click()

  await expect(page.getByTestId("research-task-title").locator("input")).toHaveValue(
    "评估候选化合物的细胞响应",
  )
  await expect(page.getByTestId("research-task-goal").locator("textarea")).toHaveValue(
    "确定在安全边界内是否存在可重现的细胞响应。",
  )
  await expect(page.getByTestId("research-task-success-criteria").locator("textarea")).toHaveValue(
    "报告预先定义的效应量和不确定性",
  )
  await expect(page.getByTestId("research-task-stop-conditions").locator("textarea")).toHaveValue(
    "达到已批准的安全阈值",
  )
  await expect(page.getByTestId("research-task-aira-guidance")).toContainText(
    "该草稿把问题限定为可观察且可审核的目标。",
  )
  expect(draftRequests).toBe(1)
  await expect(page).toHaveURL(/\/research\/tasks$/)
})

test("AI-disabled instances keep manual Research Task creation available", async ({ page }) => {
  await useChinese(page)
  await page.route(/\/api\/instance(?:\?.*)?$/, async (route) => {
    const response = await route.fetch()
    const status = await response.json()
    await route.fulfill({
      response,
      json: {
        ...status,
        ai_enabled: false,
        enabled_chat_models: [],
      },
    })
  })

  await page.goto("/research/tasks")
  await page.getByRole("button", { name: "新建科研任务", exact: true }).first().click()

  await expect(page.getByTestId("research-task-aira")).toHaveCount(0)
  await expect(page.getByTestId("research-task-title")).toBeVisible()
  await expect(page.getByText("当前 AI 不可用", { exact: false })).toBeVisible()
})

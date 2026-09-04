import { expect, test } from "@playwright/test"

test("structured Human Work is submitted, previewed, and accepted deterministically", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null }))
  })

  const now = "2026-09-04T08:00:00Z"
  const baseAction = {
    id: "action-human-1",
    run_id: "run-1",
    sequence: 1,
    plan_version: 1,
    kind: "human_work_item",
    status: "waiting_human",
    title: "记录样本观察结果",
    description: "由受派研究人员完成结构化观察。",
    executor_type: "human",
    assignee_user_id: "owner-1",
    input_data: {},
    output_data: {},
    requirements: {},
    policy_decision: "require_human",
    policy_reason: "Structured Human Work requires explicit submission and review.",
    preview_digest: "action-preview",
    revision: 1,
    created_at: now,
    updated_at: now,
    dependencies: [],
    dependent_action_ids: [],
  }
  const contract = {
    schema: "airalogy.human-work-submission.v1",
    type: "structured_values",
    completion_criteria: "记录完整且数量大于零。",
    evidence_kind: "observation",
    fields: [
      {
        key: "observation",
        label: "观察结果",
        description: "描述样本的可见变化。",
        value_type: "long_text",
        required: true,
        options: [],
        unit: "",
      },
      {
        key: "sample_count",
        label: "样本数",
        description: "本次实际观察的样本数。",
        value_type: "number",
        required: true,
        options: [],
        unit: "个",
      },
    ],
    data_asset_min_count: 0,
    data_asset_max_count: 0,
  }
  const makeItem = (status: string, revision: number, submission: Record<string, unknown> = {}) => ({
    id: "work-human-1",
    action_id: baseAction.id,
    assignee_user_id: "owner-1",
    status,
    instructions: "观察培养皿中的样本，并提交结构化结果。",
    submission_contract: contract,
    submission,
    validation_issues: [],
    revision,
    created_at: now,
    updated_at: now,
    assignee: { id: "owner-1", username: "owner", name: "Owner" },
    action: { ...baseAction, revision, status: status === "accepted" ? "completed" : "waiting_human" },
    run: {
      id: "run-1",
      task_id: "task-1",
      run_number: 1,
      status: "waiting_human",
      plan_version: 1,
      advance_generation: 1,
      environment_snapshot: {},
      aira_state: {},
      result_package: {},
      created_at: now,
      updated_at: now,
    },
    task: {
      id: "task-1",
      title: "候选样本观察",
      goal: "获得可审核的观察证据",
      status: "running",
      revision: 1,
      owner_user_id: "owner-1",
    },
    project: { id: "project-1", uid: "quickstart", name: "Quickstart" },
    lab: { id: "lab-1", uid: "dev_lab", name: "Development Lab" },
    permissions: {
      can_assign: true,
      can_start: status === "open" || status === "changes_requested",
      can_submit: ["open", "in_progress", "changes_requested"].includes(status),
      can_review: status === "submitted",
    },
  })

  let currentItem = makeItem("open", 1)
  let submissionPreviewRequests = 0
  let reviewPreviewRequests = 0
  await page.route("**/api/research-work-items/work-human-1**", async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    if (request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(currentItem) })
      return
    }
    if (path.endsWith("/start")) {
      currentItem = makeItem("in_progress", 2)
    }
    else if (path.endsWith("/submission/preview")) {
      submissionPreviewRequests += 1
      const body = request.postDataJSON() as Record<string, unknown>
      expect(body).toMatchObject({
        expected_revision: 2,
        values: { observation: "样本边缘完整，未见污染。", sample_count: 3 },
        data_asset_version_ids: [],
      })
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ preview_digest: "submission-preview", command: body, effects: ["Create a reviewable submission snapshot."] }),
      })
      return
    }
    else if (path.endsWith("/submission")) {
      const body = request.postDataJSON() as Record<string, unknown>
      expect(body.preview_digest).toBe("submission-preview")
      currentItem = makeItem("submitted", 3, {
        values: { observation: "样本边缘完整，未见污染。", sample_count: 3 },
        data_assets: [],
        note: "第一轮观察完成。",
      })
    }
    else if (path.endsWith("/review/preview")) {
      reviewPreviewRequests += 1
      const body = request.postDataJSON() as Record<string, unknown>
      expect(body).toMatchObject({ expected_revision: 3, decision: "accept" })
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ preview_digest: "review-preview", command: body, effects: ["Seal immutable evidence and release dependent actions."] }),
      })
      return
    }
    else if (path.endsWith("/review")) {
      const body = request.postDataJSON() as Record<string, unknown>
      expect(body.preview_digest).toBe("review-preview")
      currentItem = makeItem("accepted", 4, {
        values: { observation: "样本边缘完整，未见污染。", sample_count: 3 },
        data_assets: [],
        note: "第一轮观察完成。",
      })
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(currentItem) })
  })

  await page.goto("/research/work-items/work-human-1")
  await expect(page.getByTestId("human-work-status")).toContainText("待处理")
  await page.getByTestId("human-work-field-observation").locator("textarea").fill("样本边缘完整，未见污染。")
  await page.getByTestId("human-work-field-sample_count").locator("input").fill("3")
  await page.getByTestId("human-work-submission-note").locator("textarea").fill("第一轮观察完成。")

  await page.getByTestId("human-work-preview-submission").click()
  await expect(page.getByText("Create a reviewable submission snapshot.")).toBeVisible()
  await page.getByTestId("human-work-confirm-submission").click()
  await expect(page.getByTestId("human-work-status")).toContainText("已提交")

  await page.getByTestId("human-work-preview-review").click()
  await expect(page.getByText("Seal immutable evidence and release dependent actions.")).toBeVisible()
  await page.getByTestId("human-work-confirm-review").click()
  await expect(page.getByTestId("human-work-status")).toContainText("已验收")
  await expect(page.getByTestId("app-shell-content").getByText(
    "Human Work 已验收并登记为已校验 Evidence",
    { exact: true },
  )).toBeVisible()
  expect(submissionPreviewRequests).toBe(1)
  expect(reviewPreviewRequests).toBe(1)
})

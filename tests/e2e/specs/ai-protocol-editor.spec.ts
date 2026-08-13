import { expect, test } from "@playwright/test"

const GENERATED_PROTOCOL = `# 细胞药物处理实验

## 基本信息

样品编号：{{var|sample_id: str}}

药物浓度：{{var|drug_concentration: float}}

## 实验步骤

{{step|prepare_cells}} 准备细胞并加入药物。
`

const UPDATED_PROTOCOL = `# 细胞药物处理实验

## 基本信息

样品编号：{{var|sample_id: str}}

试剂批号：{{var|reagent_lot: str}}

药物浓度：{{var|drug_concentration: float}}

## 实验步骤

{{step|prepare_cells}} 准备细胞并加入药物。
`

test("non-technical user can create and refine a Protocol with Aira", async ({ page }) => {
  await page.route("**/api/editor/protocol_generate_aimd", async (route) => {
    const request = route.request()
    const body = request.postDataJSON() as { instruction: string }
    expect(body.instruction).toContain("细胞药物处理")
    await route.fulfill({
      status: 200,
      contentType: "text/plain; charset=utf-8",
      body: GENERATED_PROTOCOL,
    })
  })

  await page.goto(`/editor?package_id=e2e-ai-${Date.now()}`)
  await page.getByTestId("ai-protocol-create").click()
  await page.getByTestId("ai-protocol-name").locator("input").fill("细胞药物处理实验")
  await page.getByTestId("ai-protocol-requirements").locator("textarea").fill(
    "创建细胞药物处理实验，记录样品编号和药物浓度，并包含准备细胞步骤。",
  )
  await page.getByTestId("ai-protocol-generate").click()

  const aiEditPanel = page.getByTestId("editor-ai-edit-panel")
  await expect(aiEditPanel).toBeVisible()
  await expect.poll(async () => (await aiEditPanel.boundingBox())?.width || 0).toBeGreaterThanOrEqual(400)
  await expect(aiEditPanel.getByRole("heading", { name: /Aira Protocol 助手|Aira Protocol Assistant/ })).toBeVisible()
  await expect(aiEditPanel).toContainText(/安全修改自动应用|Safe changes apply automatically/)

  const input = aiEditPanel.getByTestId("chat-input").locator("[contenteditable='true']")
  await page.route("**/api/editor/code_edit", async (route) => {
    const body = route.request().postDataJSON() as { prompt: string }
    expect(body.prompt).toContain("为什么")
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        runtime: "opencode",
        message: "药物浓度会直接影响细胞响应，记录它有助于复现实验并比较不同处理组。",
        edit_status: "no_changes",
        changed_files: [],
        warnings: [],
        execution_log: [],
      }),
    })
  })

  await input.fill("为什么这个 Protocol 要记录药物浓度？")
  await aiEditPanel.getByTestId("chat-submit").click()
  await expect(aiEditPanel.getByText("药物浓度会直接影响细胞响应，记录它有助于复现实验并比较不同处理组。", { exact: true })).toBeVisible()
  await expect(aiEditPanel).not.toContainText(/Aira 没有修改当前 Protocol|Aira did not change the current Protocol/)
  await expect(page.locator(".monaco-editor .view-lines").first()).not.toContainText("试剂批号")

  await page.unroute("**/api/editor/code_edit")

  await page.route("**/api/editor/code_edit", async (route) => {
    const request = route.request()
    const body = request.postDataJSON() as { prompt: string, files: Array<{ path: string, content: string }> }
    expect(body.prompt).toContain("批号")
    expect(body.files.find(file => file.path === "protocol.aimd")?.content).toContain("药物浓度")
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        runtime: "opencode",
        message: "已新增试剂批号字段。",
        edit_status: "changed",
        changed_files: [{
          path: "protocol.aimd",
          name: "protocol.aimd",
          type: "aimd",
          status: "modified",
          content: UPDATED_PROTOCOL,
          diff: "@@ -5,0 +6,2 @@\n+试剂批号：{{var|reagent_lot: str}}",
        }],
        warnings: [],
        execution_log: [],
      }),
    })
  })

  await input.fill("新增一个必填的试剂批号字段。")
  await aiEditPanel.getByTestId("chat-submit").click()

  const review = page.getByTestId("editor-ai-review")
  await expect(review).toBeHidden()

  const changeStatus = aiEditPanel.getByTestId("editor-ai-change-status")
  await expect(changeStatus).toBeVisible()
  await expect(changeStatus).toContainText(/已自动应用|Applied/)
  await expect(page.locator(".monaco-editor .view-lines").first()).toContainText("试剂批号")

  await aiEditPanel.getByTestId("editor-ai-view-changes").click()
  await expect(review).toBeVisible()
  await expect(review.getByTestId("editor-ai-change-summary")).toContainText("已新增试剂批号字段")
  await expect(review.getByText(/实验流程与记录字段|Experimental flow and record fields/).first()).toBeVisible()
  await expect(review.getByTestId("editor-ai-apply-all")).toHaveCount(0)
  await review.getByText(/查看详细差异|View detailed differences/).click()
  const diffView = review.getByTestId("editor-ai-diff-protocol.aimd")
  await expect(diffView).toBeVisible()
  await expect(diffView.locator(".monaco-diff-editor")).toHaveCount(1)
  await expect.poll(async () => (await diffView.locator(".monaco-diff-editor").boundingBox())?.height || 0).toBeGreaterThanOrEqual(300)
  await expect(diffView).toHaveAttribute("data-view-mode", "inline")
  await review.getByTestId("editor-ai-diff-side-by-side-protocol.aimd").click()
  await expect(diffView).toHaveAttribute("data-view-mode", "side-by-side")
  await review.getByRole("button", { name: /关闭|Close/, exact: true }).click()
  await expect(review).toBeHidden()

  await aiEditPanel.getByTestId("editor-ai-undo").click()
  await expect(changeStatus).toBeHidden()
  await expect(page.locator(".monaco-editor .view-lines").first()).not.toContainText("试剂批号")

  await page.unroute("**/api/editor/code_edit")
  await page.route("**/api/editor/code_edit", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        runtime: "opencode",
        message: "这个修改需要确认。",
        edit_status: "changed",
        changed_files: [{
          path: "protocol.aimd",
          name: "protocol.aimd",
          type: "aimd",
          status: "modified",
          content: UPDATED_PROTOCOL,
          diff: "@@ -5,0 +6,2 @@\n+试剂批号：{{var|reagent_lot: str}}",
        }],
        warnings: ["请确认新字段是否需要兼容历史记录。"],
        execution_log: [],
      }),
    })
  })

  await input.fill("再添加试剂批号字段。")
  await aiEditPanel.getByTestId("chat-submit").click()
  await expect(review).toBeVisible()
  await expect(review.getByTestId("editor-ai-apply-all")).toBeVisible()
  await expect(page.locator(".monaco-editor .view-lines").first()).not.toContainText("试剂批号")
})

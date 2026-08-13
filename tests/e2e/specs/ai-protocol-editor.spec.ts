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
  await expect(aiEditPanel.getByRole("heading", { name: /让 Aira 修改 Protocol|Edit with Aira/ })).toBeVisible()

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

  const input = aiEditPanel.getByTestId("chat-input").locator("[contenteditable='true']")
  await input.fill("新增一个必填的试剂批号字段。")
  await aiEditPanel.getByTestId("chat-submit").click()

  const review = page.getByTestId("editor-ai-review")
  await expect(review).toBeVisible()
  await expect(review.getByText(/实验流程与记录字段|Experimental flow and record fields/)).toBeVisible()
  await review.getByTestId("editor-ai-apply-all").click()
  await expect(review).toBeHidden()
})

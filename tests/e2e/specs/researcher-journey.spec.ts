import { expect, test } from "@playwright/test"

// Successful writes and capability discovery use the real isolated API.
// Only failure tests inject unavailable network/storage boundaries.
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null }))
  })
})

test("researcher imports a private Paper, writes Knowledge, and reopens the saved note", async ({ page }) => {
  const title = `Journey paper ${Date.now()} — synthetic metadata`
  await page.goto("/knowledge")
  await page.getByRole("button", { name: "Import paper", exact: true }).first().click()
  const dialog = page.getByRole("dialog")
  await dialog.getByText("DOI", { exact: true }).first().click()
  await page.getByText("Manual metadata", { exact: true }).click()
  await dialog.getByPlaceholder("Enter the published title").fill(title)
  await dialog.getByPlaceholder("One author per line").fill("Test Researcher")
  await dialog.getByRole("button", { name: "Preview import", exact: true }).click()
  await expect(dialog).toContainText("My Knowledge")
  await expect(dialog).toContainText("Only me")
  await dialog.getByRole("button", { name: "Confirm import", exact: true }).click()
  await page.getByRole("button", { name: "Create Knowledge from paper", exact: true }).click()
  await expect(page.getByTestId("knowledge-title").locator("input")).toHaveValue(title)
  await page.getByTestId("knowledge-body").locator("textarea").fill("Synthetic test note with uncertainty preserved; no scientific finding is asserted.")
  await page.getByTestId("knowledge-create-confirm").click()
  await expect(page.getByRole("dialog")).toHaveCount(0)
  await expect(page.getByRole("article").getByRole("heading", { name: title, exact: true })).toBeVisible()
  await page.reload()
  await page.getByText("Knowledge Notes", { exact: true }).click()
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible()
  await expect(page.getByText("Synthetic test note with uncertainty preserved; no scientific finding is asserted.", { exact: true })).toBeVisible()
})

test("failed Knowledge writes retain text and show persistent retry guidance", async ({ page }) => {
  await page.goto("/knowledge")
  await page.getByRole("button", { name: "New Knowledge", exact: true }).click()
  await page.getByTestId("knowledge-title").locator("input").fill("Unsaved synthetic note")
  await page.getByTestId("knowledge-body").locator("textarea").fill("Keep this draft when the network fails.")
  await page.route("**/api/knowledge/items/preview", route => route.abort("failed"))
  await page.getByTestId("knowledge-create-confirm").click()
  await expect(page.getByTestId("knowledge-save-error")).toBeVisible()
  await expect(page.getByTestId("knowledge-body").locator("textarea")).toHaveValue("Keep this draft when the network fails.")
  await page.unroute("**/api/knowledge/items/preview")
  await page.getByTestId("knowledge-create-confirm").click()
  await expect(page.getByRole("heading", { name: "Unsaved synthetic note", exact: true })).toBeVisible()
})

test("minimal manual Research Task does not require optional infrastructure", async ({ page }) => {
  const instance = await page.request.get("/api/instance")
  expect(instance.ok()).toBeTruthy()
  const { ai_enabled: aiEnabled } = await instance.json()
  await page.goto("/research/tasks")
  await page.getByRole("button", { name: "New Research Task", exact: true }).first().click()
  const dialog = page.getByRole("dialog")
  await expect(dialog).toContainText("Quickstart Protocol Testing")
  if (!aiEnabled)
    await expect(dialog.getByText("Autonomy level", { exact: true })).toHaveCount(0)
  await expect(page.getByTestId("research-task-environment")).not.toHaveAttribute("open", "")
  await expect(page.getByTestId("research-task-environment-summary")).toContainText("1 tools")
  await page.getByTestId("research-task-title").locator("input").fill("Journey — synthetic observation")
  await page.getByTestId("research-task-goal").locator("textarea").fill("Verify that a researcher can organize a manual observation without AI.")
  await page.getByTestId("research-task-success-criteria").locator("textarea").fill("A traceable observation is available for review.")
  await dialog.getByRole("button", { name: "Preview Task", exact: true }).click()
  await expect(dialog).toContainText("No limit")
  await dialog.getByRole("button", { name: "Confirm and create", exact: true }).click()
  await expect(page.getByRole("heading", { name: "Journey — synthetic observation", exact: true })).toBeVisible()
  if (!aiEnabled) {
    await page.getByRole("button", { name: "Start Task", exact: true }).click()
    await expect(page.getByTestId("research-manual-next-step")).toBeVisible()
    await expect(page.getByText("Aira stage", { exact: true })).toHaveCount(0)
    await page.getByRole("button", { name: "Add Human Work", exact: true }).click()
    const humanDialog = page.getByRole("dialog")
    await humanDialog.getByPlaceholder("For example: Inspect sample labels").fill("Synthetic label inspection")
    await humanDialog.getByPlaceholder("State exactly what the assignee must do and what must not be assumed.").fill("Record a synthetic practice observation, not research evidence.")
    await page.getByTestId("human-work-field-label").locator("input").fill("观察结果")
    await expect(page.getByTestId("human-work-field-advanced")).not.toHaveAttribute("open", "")
    await humanDialog.getByRole("button", { name: "Add field", exact: true }).click()
    await page.getByTestId("human-work-field-label").nth(1).locator("input").fill("观察结果")
    const request = page.waitForRequest(request => request.url().endsWith("/human-actions/preview") && request.method() === "POST")
    await humanDialog.getByRole("button", { name: "Preview Action", exact: true }).click()
    const fields = (await request).postDataJSON().request.fields
    expect(fields.map((field: { label: string }) => field.label)).toEqual(["观察结果", "观察结果"])
    expect(new Set(fields.map((field: { key: string }) => field.key)).size).toBe(2)
    for (const field of fields)
      expect(field.key).toMatch(/^[a-z][a-z0-9_]{0,63}$/)
    await humanDialog.getByRole("button", { name: "Confirm and assign", exact: true }).click()
    await expect(humanDialog).toHaveCount(0)
    await expect(page.getByText("Synthetic label inspection", { exact: true }).first()).toBeVisible()
  }
  else {
    // Creating the editable Task manually must not itself start an AI Run.
    await expect(page.getByRole("button", { name: "Start with Aira", exact: true })).toBeVisible()
  }
})

test("My Log is reachable and a progress entry survives reloading", async ({ page }) => {
  const title = `Journey progress ${Date.now()}`
  await page.goto("/home")
  await page.getByRole("button", { name: "My", exact: true }).click()
  await page.getByRole("button", { name: "My Log", exact: true }).click()
  await page.getByRole("button", { name: "New Log entry", exact: true }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByRole("textbox").nth(1).fill(title)
  await dialog.getByRole("textbox").nth(2).fill("Synthetic progress note; no Protocol or experimental Record is needed for this log.")
  await dialog.getByRole("button", { name: "Preview entry", exact: true }).click()
  await expect(dialog).toContainText("My Log")
  await dialog.getByRole("button", { name: "Confirm and save", exact: true }).click()
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible()
})

test("tablet workbench leads and Record draft has one reliable save entry", async ({ page }) => {
  await page.setViewportSize({ width: 850, height: 1000 })
  await page.goto("/home")
  await expect(page.getByText("Quick actions for your role", { exact: true })).toBeVisible()
  await expect(page.getByTestId("workbench-loading")).toHaveCount(0)
  const work = await page.getByTestId("home-work").boundingBox()
  const resources = await page.getByTestId("home-resources").boundingBox()
  expect(work!.y).toBeLessThan(resources!.y)
  expect(work!.width).toBeGreaterThan(700)
  await page.goto("/labs/dev_lab/projects/quickstart/protocols/drug_response_ic50_en/add")
  await expect(page.getByRole("button", { name: "Save draft", exact: true })).toHaveCount(1)
  const field = page.getByRole("textbox", { name: "study_id", exact: true })
  await field.fill("SYNTHETIC-DRAFT-01")
  await page.getByTestId("record-save-draft").click()
  await expect(page.getByText("Draft saved on this device.", { exact: true })).toBeVisible()
  await page.reload()
  await page.getByRole("button", { name: "Restore draft", exact: true }).click()
  await expect(page.getByRole("dialog")).toContainText("SYNTHETIC-DRAFT-01")
})

test("opening an empty Record form does not invent outstanding work", async ({ page }) => {
  await page.goto("/labs/dev_lab/projects/quickstart/protocols/schema_governance_e2e/add")
  await expect(page.getByTestId("record-save-draft")).toBeVisible()
  await page.getByRole("banner").getByRole("link").first().click()
  await expect(page.getByText("Quick actions for your role", { exact: true })).toBeVisible()
  await expect(page.getByText(/0 local Record drafts|No assigned research work, approval, result review, or local Record draft is waiting\./)).toBeVisible()
})

test("storage quota failure cannot claim a Record draft was saved", async ({ page }) => {
  await page.addInitScript(() => {
    const original = Storage.prototype.setItem
    Storage.prototype.setItem = function (key, value) {
      if (key === "unitRecordDraft")
        throw new DOMException("Injected test quota failure", "QuotaExceededError")
      return original.call(this, key, value)
    }
  })
  await page.goto("/labs/dev_lab/projects/quickstart/protocols/drug_response_ic50_en/add")
  await page.getByRole("textbox", { name: "study_id", exact: true }).fill("UNSAVED-SYNTHETIC-DRAFT")
  await page.getByTestId("record-save-draft").click()
  await expect(page.getByRole("alert")).toContainText("Draft not saved")
  await expect(page.getByText("Draft saved on this device.", { exact: true })).toHaveCount(0)
})

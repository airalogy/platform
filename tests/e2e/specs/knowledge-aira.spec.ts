import { expect, test } from "@playwright/test"

const entryId = "018f0000-0000-7000-8000-000000000101"
const paperId = "018f0000-0000-7000-8000-000000000102"
const generationId = "018f0000-0000-7000-8000-000000000103"

const paperEntry = {
  id: entryId,
  scope_type: "personal",
  owner_user_id: "018f0000-0000-7000-8000-000000000001",
  lab_id: null,
  project_id: null,
  visibility: "private",
  tags: ["assay"],
  notes: "Check whether the result is independently reproduced.",
  source_type: "doi",
  source_url: null,
  source_metadata: {},
  paper: {
    id: paperId,
    doi: "10.1000/airalogy.e2e",
    title: "A bounded assay result",
    abstract: "The Paper reports one bounded assay response.",
    publication_year: 2026,
    first_author: "Alice Researcher",
    authors: ["Alice Researcher"],
    venue: "Airalogy Research",
    identifiers: {},
    candidate_fingerprint: "a".repeat(64),
    metadata_source: "doi",
    created_at: "2026-09-04T00:00:00Z",
    updated_at: "2026-09-04T00:00:00Z",
  },
  files: [],
  project_ids: [],
  collection_ids: [],
  created_at: "2026-09-04T00:00:00Z",
  updated_at: "2026-09-04T00:00:00Z",
}

function useChinese(page: import("@playwright/test").Page) {
  return page.addInitScript(() => {
    window.localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null }))
  })
}

async function mockPaperLibrary(
  page: import("@playwright/test").Page,
  entry: Record<string, unknown> = paperEntry,
) {
  await page.route(/\/api\/knowledge\/papers(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [entry], page: 1, page_size: 20 }),
    })
  })
  await page.route(`**/api/knowledge/papers/${entryId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(entry),
    })
  })
  await page.route(/\/api\/knowledge\/collections(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [] }),
    })
  })
}

test("Aira turns an authorized Paper into editable Suggested Knowledge", async ({ page }) => {
  await useChinese(page)
  await mockPaperLibrary(page)
  await page.route(/\/api\/instance(?:\?.*)?$/, async (route) => {
    const response = await route.fetch()
    const status = await response.json()
    await route.fulfill({ response, json: { ...status, ai_enabled: true } })
  })

  const generation = {
    id: generationId,
    model: "e2e-model",
    generated_at: "2026-09-04T00:00:00Z",
    context_digest: "c".repeat(64),
    instruction: "",
    source_snapshot: {
      library_entry_id: entryId,
      entry_digest: "d".repeat(64),
      paper_digest: "e".repeat(64),
      files: [],
    },
    output: {
      title: "A bounded assay finding",
      kind: "finding",
      body: "The Paper reports one bounded response; independent validation is missing.",
      tags: ["assay", "reported-result"],
      rationale: "This is a reported finding, not an adopted decision.",
      assumptions: ["The reported endpoint matches the intended use."],
      warnings: ["Independent replication is not supplied."],
    },
  }
  await page.route(`**/api/knowledge/papers/${entryId}/knowledge-draft-with-aira`, async (route) => {
    expect(route.request().postDataJSON()).toEqual({
      instruction: "",
      confirm_restricted_processing: false,
    })
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        draft: {
          title: generation.output.title,
          kind: generation.output.kind,
          body: generation.output.body,
          tags: generation.output.tags,
        },
        rationale: generation.output.rationale,
        assumptions: generation.output.assumptions,
        warnings: generation.output.warnings,
        source: generation.source_snapshot,
        aira_generation: generation,
        aira_receipt: "signed-e2e-receipt",
      }),
    })
  })

  let previewPayload: Record<string, unknown> | undefined
  let createPayload: Record<string, unknown> | undefined
  await page.route("**/api/knowledge/items/preview", async (route) => {
    previewPayload = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        preview_digest: "f".repeat(64),
        command: {},
        effect: {
          state: "draft",
          generated_by: "aira_assisted",
          requires_human_review: true,
        },
      }),
    })
  })
  await page.route(/\/api\/knowledge\/items$/, async (route) => {
    createPayload = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "018f0000-0000-7000-8000-000000000104",
        scope_type: "personal",
        owner_user_id: paperEntry.owner_user_id,
        lab_id: null,
        project_id: null,
        visibility: "private",
        kind: "finding",
        state: "draft",
        title: "A bounded assay finding",
        body: "Edited candidate with uncertainty retained.",
        tags: generation.output.tags,
        revision: 1,
        derived_from_id: null,
        generated_by: "aira_assisted",
        generation_id: generationId,
        generation_model: "e2e-model",
        generation_snapshot: generation,
        created_by_user_id: paperEntry.owner_user_id,
        reviewed_by_user_id: null,
        reviewed_at: null,
        paper_library_entry_ids: [entryId],
        research_file_ids: [],
        evidence_sources: [],
        created_at: "2026-09-04T00:00:00Z",
        updated_at: "2026-09-04T00:00:00Z",
      }),
    })
  })
  await page.route(/\/api\/knowledge\/items\?.*$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], page: 1, page_size: 20 }),
    })
  })

  await page.goto("/knowledge")
  await page.getByRole("button", { name: /A bounded assay result/ }).click()
  await page.getByTestId("paper-aira-knowledge-draft").click()

  await expect(page.getByTestId("knowledge-title").locator("input")).toHaveValue(
    "A bounded assay finding",
  )
  await expect(page.getByText("Independent replication is not supplied.")).toBeVisible()
  await page.getByTestId("knowledge-body").locator("textarea").fill(
    "Edited candidate with uncertainty retained.",
  )
  await page.getByTestId("knowledge-create-confirm").click()

  await expect.poll(() => createPayload).toBeTruthy()
  expect(previewPayload?.aira_receipt).toBe("signed-e2e-receipt")
  expect(previewPayload?.paper_library_entry_ids).toEqual([entryId])
  expect(createPayload?.preview_digest).toBe("f".repeat(64))
  expect(createPayload?.body).toBe("Edited candidate with uncertainty retained.")
  expect((createPayload?.aira_generation as { id: string }).id).toBe(generationId)
})

test("AI-disabled Knowledge keeps the manual Paper path and hides Aira", async ({ page }) => {
  await useChinese(page)
  await mockPaperLibrary(page)
  await page.route(/\/api\/instance(?:\?.*)?$/, async (route) => {
    const response = await route.fetch()
    const status = await response.json()
    await route.fulfill({
      response,
      json: { ...status, ai_enabled: false, enabled_chat_models: [] },
    })
  })

  await page.goto("/knowledge")
  await page.getByRole("button", { name: /A bounded assay result/ }).click()

  await expect(page.getByTestId("paper-aira-knowledge-draft")).toHaveCount(0)
  await expect(page.getByRole("button", { name: "从论文创建 Knowledge" })).toBeVisible()
})

test("Aira requires confirmation for an authorized Restricted PDF source", async ({ page }) => {
  await useChinese(page)
  const restrictedEntry = {
    ...paperEntry,
    files: [
      {
        id: "018f0000-0000-7000-8000-000000000105",
        filename: "restricted-paper.pdf",
        content_type: "application/pdf",
        size_bytes: 1024,
        relationship_type: "full_text",
        visibility: "restricted",
      },
    ],
  }
  await mockPaperLibrary(page, restrictedEntry)
  await page.route(/\/api\/instance(?:\?.*)?$/, async (route) => {
    const response = await route.fetch()
    const status = await response.json()
    await route.fulfill({ response, json: { ...status, ai_enabled: true } })
  })

  let confirmedRestrictedProcessing = false
  await page.route(`**/api/knowledge/papers/${entryId}/knowledge-draft-with-aira`, async (route) => {
    const payload = route.request().postDataJSON() as {
      confirm_restricted_processing?: boolean
    }
    confirmedRestrictedProcessing = payload.confirm_restricted_processing === true
    const output = {
      title: "Restricted source candidate",
      kind: "finding",
      body: "Editable candidate from an explicitly confirmed source.",
      tags: ["restricted-source"],
      rationale: "The source remains governed.",
      assumptions: [],
      warnings: ["Confirm independently."],
    }
    const generation = {
      id: generationId,
      model: "e2e-model",
      generated_at: "2026-09-04T00:00:00Z",
      context_digest: "c".repeat(64),
      instruction: "",
      source_snapshot: {
        library_entry_id: entryId,
        entry_digest: "d".repeat(64),
        paper_digest: "e".repeat(64),
        files: [
          {
            research_file_id: restrictedEntry.files[0].id,
            relationship_type: "full_text",
            visibility: "restricted",
          },
        ],
      },
      output,
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        draft: output,
        rationale: output.rationale,
        assumptions: output.assumptions,
        warnings: output.warnings,
        source: generation.source_snapshot,
        aira_generation: generation,
        aira_receipt: "signed-restricted-receipt",
      }),
    })
  })

  await page.goto("/knowledge")
  await page.getByRole("button", { name: /A bounded assay result/ }).click()
  await page.getByTestId("paper-aira-knowledge-draft").click()

  const dialog = page.locator(".n-dialog")
  await expect(dialog.getByText("确认用 Aira 处理 Restricted 内容？")).toBeVisible()
  await dialog.getByRole("button", { name: "确认" }).click()

  await expect.poll(() => confirmedRestrictedProcessing).toBe(true)
  await expect(page.getByTestId("knowledge-title").locator("input")).toHaveValue(
    "Restricted source candidate",
  )
})

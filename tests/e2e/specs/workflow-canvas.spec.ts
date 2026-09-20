import type { Locator, Page } from "@playwright/test"
import type { WorkflowContext, WorkflowDefinitionDetail, WorkflowSavePreview } from "../../../apps/web/src/service/api/workflow-definitions"
import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

// Read the rendered node's local transform, not screen coordinates: fitting the
// viewport after a reload must not be mistaken for changing graph positions.
async function graphPosition(node: Locator) {
  return node.evaluate((element) => {
    const matrix = new DOMMatrixReadOnly(getComputedStyle(element).transform)
    return { x: matrix.m41, y: matrix.m42 }
  })
}

async function dragCard(page: Page, canvas: Locator, node: Locator, delta: { x: number, y: number }) {
  const before = await graphPosition(node)
  const canvasBox = (await canvas.boundingBox())!
  const titleBox = (await node.locator("strong").boundingBox())!
  const start = { x: titleBox.x + titleBox.width / 2, y: titleBox.y + titleBox.height / 2 }
  const end = { x: start.x + delta.x, y: start.y + delta.y }
  expect(end.x).toBeGreaterThan(canvasBox.x + 10)
  expect(end.x).toBeLessThan(canvasBox.x + canvasBox.width - 10)
  expect(end.y).toBeGreaterThan(canvasBox.y + 10)
  expect(end.y).toBeLessThan(canvasBox.y + canvasBox.height - 10)
  await page.mouse.move(start.x, start.y)
  await page.mouse.down()
  await page.mouse.move(end.x, end.y, { steps: 16 })
  await page.mouse.up()
  await expect.poll(async () => {
    const after = await graphPosition(node)
    return Math.abs(after.x - before.x) > 1 && Math.abs(after.y - before.y) > 1
  }).toBe(true)
  return graphPosition(node)
}

test("Desktop canvas drags distinct Protocol occurrences and connects their ports before persisting the exact graph", async ({ page }, testInfo) => {
  test.setTimeout(90_000)
  const fixtures = await loadFixtures()
  await page.setViewportSize({ width: 1600, height: 1100 })
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
  const contextResponse = page.waitForResponse(response => response.url().includes("/workflow-definitions/context?") && response.ok())
  await page.goto(`/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/workflows`)
  const context: WorkflowContext = await (await contextResponse).json()
  expect(context.capabilities.write).toBe(true)
  const protocol = context.protocols.find(item => item.id === fixtures.analysis.protocol_id)!
  expect(protocol?.versions.length).toBeGreaterThan(0)

  const title = `Synthetic canvas Workflow ${randomUUID().slice(0, 8)}`
  await page.getByTestId("workflow-title").locator("input").fill(title)
  await page.getByTestId("workflow-add-protocol").click()
  await selectVisibleOption(page, protocol.name)
  await page.getByTestId("workflow-add-card").click()
  await page.getByTestId("workflow-card-title").locator("input").fill("Canvas measurement A")
  await page.getByTestId("workflow-add-card").click()
  await page.getByTestId("workflow-card-title").locator("input").fill("Canvas measurement B")
  await page.getByTestId("workflow-card-settings").getByRole("button", { name: "Close", exact: true }).click()

  const canvas = page.getByTestId("workflow-canvas")
  await expect(canvas).toBeVisible()
  await expect(page.getByTestId("workflow-card-list")).toHaveCount(0)
  const nodes = canvas.locator(".vue-flow__node")
  await expect(nodes).toHaveCount(2)
  const first = nodes.filter({ hasText: "Canvas measurement A" })
  const second = nodes.filter({ hasText: "Canvas measurement B" })
  const firstId = (await first.getAttribute("data-id"))!
  const secondId = (await second.getAttribute("data-id"))!
  expect(firstId).toBeTruthy()
  expect(secondId).toBeTruthy()
  expect(secondId).not.toBe(firstId)
  const initialPositions = [await graphPosition(first), await graphPosition(second)]
  await canvas.scrollIntoViewIfNeeded()
  await canvas.getByRole("button", { name: "Fit", exact: true }).click()
  const movedPositions = [
    await dragCard(page, canvas, first, { x: 24, y: 60 }),
    await dragCard(page, canvas, second, { x: -18, y: -65 }),
  ]
  expect(movedPositions[0]).not.toEqual(initialPositions[0])
  expect(movedPositions[1]).not.toEqual(initialPositions[1])
  expect(await first.getAttribute("data-id")).toBe(firstId)
  expect(await second.getAttribute("data-id")).toBe(secondId)

  // Use real pointer events on the source and target handles. Do not use the
  // dependency selector, Vue internals, or an API-created graph as a shortcut.
  const sourceHandle = first.locator(".vue-flow__handle.source")
  const targetHandle = second.locator(".vue-flow__handle.target")
  await expect(sourceHandle).toBeVisible()
  await expect(targetHandle).toBeVisible()
  const sourceBox = (await sourceHandle.boundingBox())!
  const targetBox = (await targetHandle.boundingBox())!
  await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2)
  await page.mouse.down()
  await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2, { steps: 20 })
  await page.mouse.up()
  const edge = canvas.locator(".vue-flow__edge")
  await expect(edge).toHaveCount(1)
  await expect(edge).toHaveAttribute("aria-label", `Edge from ${firstId} to ${secondId}`)
  const edgeId = (await edge.getAttribute("data-id"))!
  expect(edgeId).toBeTruthy()
  await expect(page.getByTestId("workflow-error")).toHaveCount(0)

  const previewResponse = page.waitForResponse(response => response.url().endsWith("/workflow-definitions/preview") && response.request().method() === "POST")
  await page.getByTestId("workflow-preview-save").click()
  const response = await previewResponse
  expect(response.ok(), await response.text()).toBe(true)
  const preview: WorkflowSavePreview = await response.json()
  expect(preview.graph.nodes.map(node => node.node_id)).toEqual([firstId, secondId])
  expect(preview.graph.edges).toEqual([{ edge_id: edgeId, source_node_id: firstId, target_node_id: secondId, condition: null }])
  expect(preview.pins).toHaveLength(2)
  for (const [index, node] of preview.graph.nodes.entries()) {
    expect(node).toMatchObject({ kind: "protocol", protocol_id: protocol.id, protocol_version_id: protocol.versions[0].id })
    expect(node.position.x).toBeCloseTo(movedPositions[index].x, 3)
    expect(node.position.y).toBeCloseTo(movedPositions[index].y, 3)
    expect(preview.pins[index]).toMatchObject({ node_id: node.node_id, protocol_id: protocol.id, protocol_version_id: protocol.versions[0].id })
  }
  const confirmation = page.waitForResponse(item => item.url().endsWith("/workflow-definitions/confirm") && item.request().method() === "POST")
  await page.getByTestId("workflow-confirm-save").click()
  const confirmedResponse = await confirmation
  expect(confirmedResponse.ok(), await confirmedResponse.text()).toBe(true)
  const saved: WorkflowDefinitionDetail = await confirmedResponse.json()
  expect(saved.revision).toBe(1)
  expect(saved.current_revision!.graph).toEqual(preview.graph)
  await expect(page.getByTestId("workflow-result")).toContainText(title)

  await page.reload()
  const loadedDefinition = page.waitForResponse(item => item.url().endsWith(`/workflow-definitions/${saved.id}`) && item.request().method() === "GET")
  await page.getByTestId("workflow-saved-item").filter({ hasText: title }).click()
  const loadedResponse = await loadedDefinition
  expect(loadedResponse.ok(), await loadedResponse.text()).toBe(true)
  const reloaded: WorkflowDefinitionDetail = await loadedResponse.json()
  expect(reloaded.current_revision!.id).toBe(saved.current_revision!.id)
  expect(reloaded.current_revision!.graph).toEqual(preview.graph)
  await expect(canvas).toBeVisible()
  await expect(nodes).toHaveCount(2)
  expect(await first.getAttribute("data-id")).toBe(firstId)
  expect(await second.getAttribute("data-id")).toBe(secondId)
  for (const [index, node] of [first, second].entries()) {
    await expect.poll(() => graphPosition(node)).toEqual(movedPositions[index])
  }
  await expect(edge).toHaveCount(1)
  await expect(edge).toHaveAttribute("data-id", edgeId)
  await expect(edge).toHaveAttribute("aria-label", `Edge from ${firstId} to ${secondId}`)
  await expect(page.getByTestId("workflow-error")).toHaveCount(0)
  await canvas.scrollIntoViewIfNeeded()
  await canvas.getByRole("button", { name: "Fit", exact: true }).click()
  await canvas.screenshot({ path: testInfo.outputPath("workflow-canvas-reloaded.png") })
})

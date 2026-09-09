import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

test("equipment integration draft survives reload and exports without enabling commands", async ({ page, request }) => {
  const fixtures = await loadFixtures()
  const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
  const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  expect(login.ok()).toBeTruthy()
  const headers = { "Auth-Token": (await login.json()).token }
  const base = `${api}/labs/${fixtures.lab.id}/resource-library`
  const definitions = await (await request.get(`${base}/definition-versions`, { headers })).json()
  const definition = definitions.items.find((item: { protocol_uid: string }) => item.protocol_uid === "plasmid_resource_definition_en")
  const suffix = Date.now()
  const typeResponse = await request.post(`${base}/types`, { headers, data: {
    protocol_version_id: definition.id,
    code: `gui_${suffix}`,
    name: "GUI synthetic equipment",
    capabilities: { booking: true },
    booking_policy: "approval",
  } })
  expect(typeResponse.ok()).toBeTruthy()
  const equipmentResponse = await request.post(`${base}/resources`, { headers, data: {
    resource_type_id: (await typeResponse.json()).id,
    name: `GUI Reader ${suffix}`,
    code: `GUI-${suffix}`,
    visibility: "lab",
    data: { construct_name: "Synthetic fixture", aliases: null, backbone: null, sequence: null, sequence_file: null, resistance_markers: null, host_species: null, copy_number: null, external_source: null, features: [] },
  } })
  expect(equipmentResponse.ok()).toBeTruthy()
  const gatewayDraft = { lab_id: fixtures.lab.id, name: `GUI gateway ${suffix}`, enabled: false }
  const preview = await (await request.post(`${api}/research-instrument-gateways/preview`, { headers, data: gatewayDraft })).json()
  const gatewayResponse = await request.post(`${api}/research-instrument-gateways`, { headers, data: { ...gatewayDraft, preview_digest: preview.preview_digest } })
  expect(gatewayResponse.ok()).toBeTruthy()
  const gateway = (await gatewayResponse.json()).gateway
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`/labs/${fixtures.lab.uid}/resources/gateways`)
  await page.getByTestId("instrument-integration-panel").getByRole("button", { name: "New integration draft", exact: true }).click()
  const modal = page.getByRole("dialog").last()
  await expect(modal).toBeVisible()
  expect((await modal.boundingBox())!.width).toBeLessThanOrEqual(358)
  await page.getByTestId("integration-equipment").click()
  await selectVisibleOption(page, `GUI Reader ${suffix}`)
  const goal = `Read instrument output ${suffix}`
  await page.getByTestId("integration-goal").locator("input").fill(goal)
  await modal.getByRole("button", { name: "Load synthetic example" }).click()
  await expect(page.getByTestId("integration-bundle").locator("textarea")).toHaveValue(/gui-rehearsal/)
  await page.getByTestId("integration-reason").locator("input").fill("Synthetic UI acceptance")
  await modal.getByRole("button", { name: "Rehearse and preview" }).click()
  await expect(page.getByTestId("integration-preview")).toContainText("hardware unverified")
  await expect(modal.getByRole("button", { name: "Confirm and save draft" })).toBeInViewport()
  await modal.getByRole("button", { name: "Confirm and save draft" }).click()
  await expect(modal).not.toBeVisible()
  await page.reload()
  const panel = page.getByTestId("instrument-integration-panel")
  await expect(panel.getByText(goal, { exact: true })).toBeVisible()
  const download = page.waitForEvent("download")
  await panel.getByRole("button", { name: "Export saved bundle" }).click()
  expect((await download).suggestedFilename()).toBe("airalogy-gui-rehearsal.json")
  await panel.getByRole("button", { name: "Revision history" }).click()
  await expect(page.getByRole("dialog").last()).toContainText("Synthetic UI acceptance")
  const commands = await (await request.get(`${api}/research-instrument-gateways/${gateway.id}/commands`, { headers })).json()
  expect(commands.items).toEqual([])
})

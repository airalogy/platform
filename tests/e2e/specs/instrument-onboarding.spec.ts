import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { instrumentWorkspaceUrl, loadFixtures, selectVisibleOption } from "./fixtures"

test("onboarding keeps one authorized equipment context across stages, reload and cancelled switching", async ({ page, request }, testInfo) => {
  const fixtures = await loadFixtures()
  const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
  const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  expect(login.ok()).toBeTruthy()
  const headers = { "Auth-Token": (await login.json()).token }
  async function call(route: string, data?: unknown) {
    const response = await request.fetch(api + route, { method: data === undefined ? "GET" : "POST", headers, data })
    expect(response.ok(), await response.text()).toBeTruthy()
    return response.json()
  }
  const suffix = Date.now()
  const base = `/labs/${fixtures.lab.id}/resource-library`
  const definitions = await call(`${base}/definition-versions`)
  const definition = definitions.items.find((item: { protocol_uid: string }) => item.protocol_uid === "plasmid_resource_definition_en")
  const kind = await call(`${base}/types`, { protocol_version_id: definition.id, code: `workspace_${suffix}`, name: "Synthetic onboarding fixtures", capabilities: { booking: true }, booking_policy: "auto" })
  const devices = []
  for (const name of ["First", "Second"]) {
    devices.push(await call(`${base}/resources`, {
      resource_type_id: kind.id,
      name: `${name} workspace reader ${suffix}`,
      code: `${name}-${suffix}`,
      visibility: "lab",
      data: { construct_name: "Synthetic fixture", aliases: null, backbone: null, sequence: null, sequence_file: null, resistance_markers: null, host_species: null, copy_number: null, external_source: null, features: [] },
    }))
  }
  const draft = { lab_id: fixtures.lab.id, name: `Workspace gateway ${suffix}`, enabled: false }
  const preview = await call("/research-instrument-gateways/preview", draft)
  const gateway = (await call("/research-instrument-gateways", { ...draft, preview_digest: preview.preview_digest })).gateway
  const anotherDraft = { ...draft, name: `Other workspace gateway ${suffix}` }
  const anotherPreview = await call("/research-instrument-gateways/preview", anotherDraft)
  const anotherGateway = (await call("/research-instrument-gateways", { ...anotherDraft, preview_digest: anotherPreview.preview_digest })).gateway
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(instrumentWorkspaceUrl(fixtures.lab.uid, gateway.id, "", "connect"))
  const context = page.getByTestId("onboarding-equipment")
  await expect(context).toBeVisible()
  await expect(page).not.toHaveURL(/instrument_resource=/)
  // Use real remote search, not the parent resource library's first page.
  await context.click()
  await context.locator("input").fill(devices[0].code)
  await selectVisibleOption(page, devices[0].name)
  await expect(page).toHaveURL(new RegExp(`instrument_resource=${devices[0].id}`))
  await page.getByTestId("onboarding-steps").getByText("Prepare adapter", { exact: true }).click()
  await page.getByTestId("onboarding-tool").click()
  await selectVisibleOption(page, "Rehearse a GUI draft")
  const panel = page.getByTestId("instrument-integration-panel")
  await panel.getByRole("button", { name: "New integration draft", exact: true }).click()
  let modal = page.getByRole("dialog").last()
  await expect(page.getByTestId("integration-equipment")).toContainText(devices[0].name)
  const goal = `Workspace context ${suffix}`
  await page.getByTestId("integration-goal").locator("input").fill(goal)
  await modal.getByRole("button", { name: "Load synthetic example" }).click()
  await page.getByTestId("integration-reason").locator("input").fill("Synthetic onboarding acceptance")
  await modal.getByRole("button", { name: "Rehearse and preview" }).click()
  await modal.getByRole("button", { name: "Confirm and save draft" }).click()
  await expect(modal).not.toBeVisible()
  await expect(panel).toContainText(goal)
  await page.getByTestId("onboarding-steps").getByText("Install & qualify", { exact: true }).click()
  await expect(page.getByTestId("instrument-installations-panel")).toBeVisible()
  await page.getByTestId("onboarding-steps").getByText("Prepare adapter", { exact: true }).click()
  await expect(panel).toContainText(goal)
  await context.click()
  await context.locator("input").fill(devices[1].code)
  await selectVisibleOption(page, devices[1].name)
  modal = page.getByRole("dialog").last()
  await modal.getByRole("button", { name: "Cancel", exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`instrument_resource=${devices[0].id}`))
  await expect(panel).toContainText(goal)
  await context.click()
  await context.locator("input").fill(devices[1].code)
  await selectVisibleOption(page, devices[1].name)
  await page.getByRole("dialog").last().getByRole("button", { name: "Confirm", exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`instrument_resource=${devices[1].id}`))
  await expect(panel).not.toContainText(goal)
  // Hold the restored-device lookup: no unscoped history may mount meanwhile.
  let releaseLookup!: () => void
  const lookupGate = new Promise<void>((resolve) => {
    releaseLookup = resolve
  })
  const lookupUrl = (url: URL) => url.pathname.endsWith("/equipment-options") && url.searchParams.get("resource_id") === devices[1].id
  await page.route(lookupUrl, async (route) => {
    await lookupGate
    await route.continue()
  })
  try {
    await page.reload()
    await expect(context).toBeVisible()
    await expect(page.getByTestId("onboarding-steps")).toHaveCount(0)
  }
  finally {
    releaseLookup()
  }
  await expect(context).toContainText(devices[1].name)
  await expect(panel).toBeVisible()
  await page.unroute(lookupUrl)
  await expect(panel).not.toContainText(goal)
  await page.screenshot({ path: testInfo.outputPath("onboarding-mobile.png"), fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  const gatewayChoice = page.getByTestId("onboarding-gateway")
  await gatewayChoice.click()
  await selectVisibleOption(page, anotherGateway.name)
  await page.getByRole("dialog").last().getByRole("button", { name: "Cancel", exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`instrument_gateway=${gateway.id}`))
  await gatewayChoice.click()
  await selectVisibleOption(page, anotherGateway.name)
  await page.getByRole("dialog").last().getByRole("button", { name: "Confirm", exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`instrument_gateway=${anotherGateway.id}`))
  await expect(page.getByTestId("instrument-pairing-panel")).toBeVisible()
  await expect(page).not.toHaveURL(/instrument_resource=/)
  // A stale URL is not permission and must not silently select another device.
  await page.goto(instrumentWorkspaceUrl(fixtures.lab.uid, gateway.id, randomUUID(), "install"))
  await expect(page.getByTestId("instrument-onboarding")).toContainText("no longer available")
  await expect(page).not.toHaveURL(/instrument_resource=/)
  await expect(page.getByRole("button", { name: "Authorize an installation", exact: true })).toBeDisabled()
  await expect(page.getByTestId("instrument-onboarding")).toContainText("installation history")
  const saved = await call(`/instrument-integrations?gateway_id=${gateway.id}&resource_id=${devices[0].id}`)
  expect(saved.items.map((item: { goal: string }) => item.goal)).toEqual([goal])
  const other = await call(`/instrument-integrations?gateway_id=${gateway.id}&resource_id=${devices[1].id}`)
  expect(other.items).toEqual([])
  expect((await call(`/research-instrument-gateways/${gateway.id}/commands`)).items).toEqual([])
  await page.goto(instrumentWorkspaceUrl(fixtures.lab.uid, randomUUID(), "", "connect"))
  await expect(page.locator(".gateway-card__main").getByText(gateway.name, { exact: true })).toBeVisible()
  await expect(page.getByTestId("instrument-onboarding")).toHaveCount(0)
})

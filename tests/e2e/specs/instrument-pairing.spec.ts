import { createHash, randomBytes } from "node:crypto"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

test("pairing requires local identity review and never enables instrument commands", async ({ page, request }) => {
  const fixtures = await loadFixtures()
  const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
  const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  expect(login.ok()).toBeTruthy()
  const headers = { "Auth-Token": (await login.json()).token }
  const draft = { lab_id: fixtures.lab.id, name: `Pairing fixture ${Date.now()}`, enabled: false }
  const preview = await (await request.post(`${api}/research-instrument-gateways/preview`, { headers, data: draft })).json()
  const created = await request.post(`${api}/research-instrument-gateways`, { headers, data: { ...draft, preview_digest: preview.preview_digest } })
  expect(created.ok()).toBeTruthy()
  const gateway = (await created.json()).gateway
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`/labs/${fixtures.lab.uid}/resources/gateways`)
  await page.locator(".gateway-card__main").filter({ hasText: draft.name }).click()
  const panel = page.getByTestId("instrument-pairing-panel")
  await expect(panel).toBeVisible()
  expect((await panel.boundingBox())!.width).toBeLessThanOrEqual(390)
  await panel.getByRole("button", { name: "Create pairing code" }).click()
  let modal = page.getByRole("dialog").last()
  await page.getByTestId("pairing-reason").locator("input").fill("Synthetic local enrollment")
  await modal.getByRole("button", { name: "Preview", exact: true }).click()
  await modal.getByRole("button", { name: "Confirm", exact: true }).click()
  await expect(page.getByTestId("pairing-code").locator("textarea")).toHaveValue(/^aipair_/)
  const code = await page.getByTestId("pairing-code").locator("textarea").inputValue()
  const token = `aigw_${randomBytes(32).toString("base64url")}`
  const claim = await request.post(`${api}/instrument-pairings/claim`, { data: {
    code,
    gateway_id: gateway.id,
    lab_id: fixtures.lab.id,
    client_name: "Synthetic paired station",
    credential_digest: createHash("sha256").update(token).digest("hex"),
    credential_hint: token.slice(-8),
  } })
  expect(claim.ok()).toBeTruthy()
  const identity = await claim.json()
  await modal.getByRole("button", { name: "Close", exact: true }).click()
  await panel.getByRole("button", { name: "Refresh", exact: true }).click()
  await expect(panel).toContainText("Needs identity confirmation")
  await panel.getByRole("button", { name: "Preview", exact: true }).click()
  modal = page.getByRole("dialog").last()
  await expect(page.getByTestId("pairing-fingerprint")).toHaveText(identity.fingerprint)
  expect((await modal.boundingBox())!.width).toBeLessThanOrEqual(358)
  await expect(modal.getByRole("button", { name: "Confirm", exact: true })).toBeDisabled()
  await modal.getByRole("checkbox").check()
  await modal.getByRole("button", { name: "Confirm", exact: true }).click()
  await expect(modal).not.toBeVisible()
  await page.reload()
  await page.locator(".gateway-card__main").filter({ hasText: draft.name }).click()
  await expect(panel).toContainText("Paired, not qualified")
  const gateways = await (await request.get(`${api}/research-instrument-gateways?lab_id=${fixtures.lab.id}`, { headers })).json()
  expect(gateways.items.find((item: { id: string }) => item.id === gateway.id).enabled).toBe(false)
  const commands = await (await request.get(`${api}/research-instrument-gateways/${gateway.id}/commands`, { headers })).json()
  expect(commands.items).toEqual([])
  const status = await request.post(`${api}/instrument-pairings/${identity.id}/status`, { headers: { "X-Airalogy-Gateway-Token": token } })
  expect((await status.json()).state).toBe("confirmed")
})

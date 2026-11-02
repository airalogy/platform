import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { readFile } from "node:fs/promises"
import { createRequire } from "node:module"
import { expect, test } from "@playwright/test"
import { loadFixtures, selectVisibleOption } from "./fixtures"

const { zipSync, strToU8 } = createRequire(new URL("../../../apps/web/package.json", import.meta.url))("fflate")

for (const [locale, width] of [["en-US", 390], ["zh-CN", 1440]] as const) {
  test(`external tools require a human confirmation and support revocation (${locale}, ${width}px)`, async ({ page, request }, testInfo) => {
    test.setTimeout(180_000)
    page.setDefaultTimeout(15_000)
    const fixtures = await loadFixtures()
    const strings = JSON.parse(await readFile(new URL(`../../../packages/shared/src/locales/langs/${locale === "zh-CN" ? "zh-cn" : "en-us"}.json`, import.meta.url), "utf8")).externalAccess
    const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
    const signIn = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    expect(signIn.ok()).toBeTruthy()
    const headers = { "Auth-Token": (await signIn.json()).token }
    const uid = `external_${randomUUID().replaceAll("-", "")}`
    const archive = zipSync({
      "protocol.aimd": strToU8("# Synthetic external import\n{{var|value: float, ge=0, le=100}}\n{{var|group: str}}"),
      "protocol.toml": strToU8(`[airalogy_protocol]\nid="${uid}"\nname="Synthetic external import"\nversion="0.1.0"\n`),
    })
    const published = await request.post(`${api}/protocols`, { headers, multipart: {
      project_id: fixtures.project.id,
      file: { name: "external-synthetic.zip", mimeType: "application/zip", buffer: Buffer.from(archive) },
    } })
    expect(published.ok(), await published.text()).toBeTruthy()
    const { data: protocol } = await published.json()
    await page.addInitScript(language => localStorage.setItem("lang", JSON.stringify({ data: language, expire: null })), locale)
    await page.setViewportSize({ width, height: 900 })
    await page.goto(`/labs/${fixtures.lab.uid}/settings`)
    const policy = page.getByTestId("external-policy")
    await expect(policy).toBeVisible()
    const toggle = policy.getByRole("switch")
    if (await toggle.getAttribute("aria-checked") !== "true")
      await toggle.click()
    const policySaved = page.waitForResponse(response => response.url().includes(`/external-access/labs/${fixtures.lab.id}/policy`) && response.request().method() === "PUT")
    await policy.getByRole("button", { name: strings.savePolicy, exact: true }).click()
    expect((await policySaved).ok()).toBeTruthy()

    await page.goto("/users/dev_owner/settings#external-access")
    const panel = page.locator("#external-access")
    await expect(panel).toBeVisible()
    await page.getByTestId("external-grant-name").locator("input").fill(`Synthetic tool ${uid}`)
    const choices = await request.get(`${api}/external-access/dashboard`, { headers })
    const project = (await choices.json()).projects.find((p: { id: string }) => p.id === fixtures.project.id)
    await page.getByTestId("external-grant-project").click()
    await selectVisibleOption(page, project.name)
    await panel.getByRole("checkbox", { name: strings.importRecords, exact: true }).check()
    const issued = page.waitForResponse(response => response.url().endsWith("/external-access/grants") && response.request().method() === "POST")
    await page.getByTestId("external-grant-create").click()
    const issuance = await issued
    expect(issuance.ok(), await issuance.text()).toBeTruthy()
    const { token, grant } = await issuance.json()
    await expect(page.getByTestId("external-grant-token").locator("input")).toHaveValue(token)
    expect(await page.evaluate(value => JSON.stringify(localStorage).includes(value), token)).toBeFalsy()
    await panel.getByRole("button", { name: strings.dismissToken, exact: true }).click()
    await expect(page.getByTestId("external-grant-token")).toHaveCount(0)
    await page.reload()
    await expect(page.getByTestId("external-grant-token")).toHaveCount(0)

    const delegated = { Authorization: `Bearer ${token}` }
    const csv = "var.value,var.group\n2,synthetic\n"
    const previewResponse = await request.post(`${api}/external-access/tools/preview_import`, { headers: delegated, data: { protocol_id: protocol.id, csv, request_key: randomUUID() } })
    expect(previewResponse.ok(), await previewResponse.text()).toBeTruthy()
    const operation = await previewResponse.json()
    expect(operation.state).toBe("pending")
    const execute = () => request.post(`${api}/external-access/tools/execute_operation`, { headers: delegated, data: { operation_id: operation.id } })
    expect((await execute()).status()).toBe(409)
    await panel.getByRole("button", { name: strings.refresh, exact: true }).click()
    await page.getByTestId(`external-operation-${operation.id}`).getByRole("button").click()
    const dialog = page.getByTestId("external-operation-dialog")
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText("Synthetic external import")
    await expect(dialog.locator("textarea")).toHaveValue(csv)
    const approve = dialog.getByRole("button", { name: strings.approve, exact: true })
    await expect(approve).toBeDisabled()
    await dialog.getByRole("checkbox", { name: strings.reviewed, exact: true }).check()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    const box = await dialog.boundingBox()
    expect(box!.width).toBeLessThanOrEqual(width - 30)
    await page.screenshot({ path: testInfo.outputPath(`external-preview-${locale}.png`) })
    const approved = page.waitForResponse(response => response.url().endsWith(`/operations/${operation.id}/decision`))
    await approve.click()
    expect((await approved).ok()).toBeTruthy()
    const execution = await execute()
    expect(execution.ok(), await execution.text()).toBeTruthy()
    const result = await execution.json()
    expect(result.result.imported_count).toBe(1)
    const repeated = await execute()
    expect((await repeated.json()).result.record_ids).toEqual(result.result.record_ids)
    await page.goto(result.result.links[0])
    await expect(page).toHaveURL(/\/record\/[^/]+\/v1$/)
    await expect(page.getByRole("button", { name: locale === "en-US" ? "Revise" : "修订", exact: true })).toBeVisible()

    await page.goto("/users/dev_owner/settings#external-access")
    await page.getByTestId(`external-grant-${grant.id}`).getByRole("button", { name: strings.revoke, exact: true }).click()
    const revoked = page.waitForResponse(response => response.url().endsWith(`/external-access/grants/${grant.id}`) && response.request().method() === "DELETE")
    await page.locator(".n-popconfirm__action").getByRole("button").last().click()
    expect((await revoked).ok()).toBeTruthy()
    const denied = await request.post(`${api}/external-access/tools/access_context`, { headers: delegated, data: {} })
    expect(denied.status()).toBe(401)
  })
}

import { Buffer } from "node:buffer"
import { createServer } from "node:http"
import { createRequire } from "node:module"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

const { zipSync, strToU8 } = createRequire(new URL("../../../apps/web/package.json", import.meta.url))("fflate")

test("one Aira conversation explains, fills, confirms an overwrite and isolates examples", async ({ page, request }) => {
  test.skip(process.env.AI_ENABLED === "false", "The AI-disabled case verifies the manual entry.")
  test.setTimeout(120000)
  page.setDefaultTimeout(15000)
  let releaseModel: (() => void) | undefined
  const calls: Array<{ references: string[], last_applied: string[], current_message: string, conversation: unknown[] }> = []
  const server = createServer(async (req, res) => {
    if (req.url !== "/api/endpoints/chat/field_input/turn") {
      res.writeHead(404).end()
      return
    }
    const parts = []
    for await (const part of req) parts.push(part)
    const data = JSON.parse(Buffer.concat(parts).toString())
    if (data.current_message === "unavailable") {
      res.writeHead(503, { "Content-Type": "application/json" }).end(JSON.stringify({ detail: "Synthetic model unavailable" }))
      return
    }
    calls.push(data)
    if (data.current_message.includes("hold"))
      await new Promise<void>((resolve) => { releaseModel = resolve })
    const op = (rf_name: string, rf_value: string | number) => ({ operation: "update", rf_name, rf_value, source: String(rf_value) })
    const intent = data.current_message.includes("simulate") ? "simulate" : data.current_message.startsWith("Explain") ? "answer" : "fill"
    const operations = intent !== "fill" ? [] : data.current_message.includes("25") ? [op("minutes", 25)] : [op("label", "001"), op("minutes", 20)]
    res.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify({
      intent,
      answer: intent === "answer" ? "Label is an identifier; minutes is duration." : "Recorder suggestion",
      references: ["label", "minutes"],
      operations,
    }))
  })
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject).listen(41999, "127.0.0.1", resolve)
  })
  try {
    const fx = await loadFixtures()
    const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
    const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
    const uid = `recorder_${Date.now()}`
    const archive = zipSync({ "protocol.aimd": strToU8("# Recorder\nLabel: {{var|label: str}}\nMinutes: {{var|minutes: int}}\nNote: {{var|note: str}}"), "protocol.toml": strToU8(`[airalogy_protocol]\nid="${uid}"\nname="Recorder test"\nversion="0.1.0"\n`) })
    const published = await request.post(`${api}/protocols`, { headers: { "Auth-Token": (await login.json()).token }, multipart: { project_id: fx.project.id, file: { name: "recorder.zip", mimeType: "application/zip", buffer: Buffer.from(archive) } } })
    expect(published.ok(), await published.text()).toBeTruthy()
    await page.goto(`/labs/${fx.lab.uid}/projects/${fx.project.uid}/protocols/${uid}/add`)
    await page.locator("[data-tab=ai-assistant]").click()
    const editor = page.getByTestId("chat-input").locator("[contenteditable=true]")
    const say = async (message: string, status = 200) => {
      await editor.fill(message)
      const result = page.waitForResponse(r => r.url().endsWith("/chats/qa/message"))
      await editor.press("Enter")
      const response = await result
      expect(response.status()).toBe(status)
    }
    const field = (id: string) => page.locator(".record-inline-content").getByRole("textbox", { name: new RegExp(`^${id}$`, "i") })
    await say("Explain label and minutes, is 37 a recommended value?")
    await expect(page.getByText("Label is an identifier; minutes is duration.").first()).toBeVisible()
    await expect(field("minutes")).toHaveValue("")
    await say("Fill those two with 001 and 20")
    await expect(page.getByTestId("recorder-receipt")).toContainText("minutes")
    await expect(field("label")).toHaveValue("001")
    await expect(field("minutes")).toHaveValue("20")
    await say("Change the second to 25")
    await expect(page.getByRole("dialog")).toContainText("20 → 25")
    await page.getByRole("dialog").getByRole("button", { name: "Confirm", exact: true }).click()
    await expect(field("minutes")).toHaveValue("25")
    await page.getByRole("button", { name: "Undo this fill" }).click()
    await expect(field("minutes")).toHaveValue("20")
    await say("Please simulate the remaining fields")
    await expect(page.getByTestId("recorder-receipt")).toContainText("Simulated")
    await expect(page.getByRole("button", { name: "Submit", exact: true })).toBeDisabled()
    await expect(page.getByTestId("record-save-draft")).toBeDisabled()
    await expect(page.locator(".simulated-record-preview")).toContainText("Example")
    await page.getByRole("button", { name: "Exit simulation" }).click()
    await expect(field("note")).toHaveValue("")
    await expect(field("label")).toHaveValue("001")
    const pending = say("Change the second to 25; hold for a moment")
    await expect.poll(() => Boolean(releaseModel)).toBe(true)
    await field("minutes").fill("31")
    await field("minutes").blur()
    releaseModel!()
    await pending
    await expect(page.getByTestId("recorder-receipt")).toContainText("Skipped")
    await expect(field("minutes")).toHaveValue("31")
    await expect(page.getByRole("dialog")).toHaveCount(0)
    await say("unavailable", 503)
    await expect(field("minutes")).toHaveValue("31")
    await page.getByTestId("record-save-draft").click()
    const draft = await page.evaluate(() => localStorage.getItem("unitRecordDraft"))
    expect(draft).toContain("001")
    expect(draft).toContain("31")
    expect(draft).not.toContain("Example")
    const records = await request.get(`${api}/protocols/${(await published.json()).data.id}/records`, { headers: { "Auth-Token": (await login.json()).token } })
    expect((await records.json()).total_count).toBe(0)
    await page.setViewportSize({ width: 390, height: 844 })
    await expect(page.getByTestId("recorder-receipt")).toBeVisible()
    const viewerLogin = await request.post(`${api}/signin_by_email`, { data: { email: "dev.viewer@airalogy.dev", password: "AiralogyDev123!" } })
    const denied = await request.post(`${api}/chats/qa/message`, { headers: { "Auth-Token": (await viewerLogin.json()).token }, data: {
      protocol_id: (await published.json()).data.id,
      context: {},
      model: { model_type: 1 },
      message: { role: "user", content: "fill" },
      recorder_target: { form_id: "viewer-form-01234", request_id: "viewer-turn-01234", version: "0.1.0" },
    } })
    expect([400, 403]).toContain(denied.status())
    expect(calls).toHaveLength(5)
    expect(calls[1].references).toEqual(["label", "minutes"])
    expect(calls[2].last_applied).toEqual(["label", "minutes"])
    expect(calls[1].conversation.length).toBeGreaterThanOrEqual(2)
    // Only the separate human submission creates a Record, using real inputs.
    await page.setViewportSize({ width: 1280, height: 844 })
    await field("note").fill("Synthetic browser observation")
    await field("note").blur()
    await page.getByRole("button", { name: "Submit", exact: true }).click()
    await page.getByRole("dialog").getByRole("button", { name: "Submit Record", exact: true }).click()
    await expect(page.getByRole("button", { name: "View saved Record", exact: true })).toBeVisible()
    const committed = await request.get(`${api}/protocols/${(await published.json()).data.id}/records`, { headers: { "Auth-Token": (await login.json()).token } })
    const saved = await committed.json()
    expect(saved.total_count).toBe(1)
    expect(saved.records[0].data.var).toMatchObject({ label: "001", minutes: 31, note: "Synthetic browser observation" })
    await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "zh-CN", expire: null })))
    await page.goto(`/labs/${fx.lab.uid}/projects/${fx.project.uid}/protocols/${uid}/add`)
    await page.locator("[data-tab=ai-assistant]").click()
    await say("simulate")
    await expect(page.getByTestId("recorder-receipt")).toContainText("模拟试填")
    await expect(page.getByRole("button", { name: "退出试填" })).toBeVisible()
  }
  finally {
    releaseModel?.()
    server.closeAllConnections()
    await new Promise<void>(resolve => server.close(() => resolve()))
  }
})

test("manual Record entry remains usable with Aira disabled", async ({ page }) => {
  test.skip(process.env.AI_ENABLED !== "false", "Only for the AI-disabled deployment")
  const fx = await loadFixtures()
  await page.goto(`/labs/${fx.lab.uid}/projects/${fx.project.uid}/protocols/${fx.analysis.protocol_uid}/add`)
  await expect(page.getByTestId("record-save-draft")).toBeVisible()
  await expect(page.locator("[data-tab=ai-assistant]")).toHaveCount(0)
  await expect(page.locator(".record-inline-content input").first()).toBeVisible()
})

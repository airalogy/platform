import { Buffer } from "node:buffer"
import { createRequire } from "node:module"
import { expect, test } from "@playwright/test"
import { loadFixtures } from "./fixtures"

const { zipSync, strToU8, unzipSync, strFromU8 } = createRequire(new URL("../../../apps/web/package.json", import.meta.url))("fflate")
const aimd = `# Synthetic client calculation
Input: {{var|a: float, ge=0}}
Double: {{var|b: float, ge=0}}
Next: {{var|c: float, ge=0}}
\`\`\`assigner runtime=client
assigner(
  {mode: "auto", dependent_fields: ["a"], assigned_fields: ["b"]},
  function double_a({a}) { return {b: a === 13 ? -1 : a * 2}; }
);
\`\`\`
\`\`\`assigner runtime=client
assigner(
  {mode: "auto", dependent_fields: ["b"], assigned_fields: ["c"]},
  function next_b({b}) { return {c: b + 1}; }
);
\`\`\`
`

test("client calculations persist and both Protocol archives round-trip", async ({ page, request }) => {
  test.setTimeout(180_000)
  page.setDefaultTimeout(15_000)
  const fixtures = await loadFixtures()
  const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
  const signIn = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  const headers = { "Auth-Token": (await signIn.json()).token }
  const uid = `client_${Date.now()}`
  const archive = zipSync({
    "protocol.aimd": strToU8(aimd),
    "protocol.toml": strToU8(`[airalogy_protocol]\nid="${uid}"\nname="Synthetic client calculation"\nversion="0.1.0"\n`),
  })
  const published = await request.post(`${api}/protocols`, { headers, multipart: {
    project_id: fixtures.project.id,
    file: { name: "synthetic.zip", mimeType: "application/zip", buffer: Buffer.from(archive) },
  } })
  expect(published.ok(), await published.text()).toBeTruthy()
  const { data: protocol } = await published.json()
  const path = `/labs/${fixtures.lab.uid}/projects/${fixtures.project.uid}/protocols/${protocol.uid}`
  await page.addInitScript(() => localStorage.setItem("lang", JSON.stringify({ data: "en-US", expire: null })))
  await page.goto(`${path}/add`)
  const serverAssignments: string[] = []
  page.on("request", (req) => {
    if (new URL(req.url()).pathname.endsWith("/var_assign"))
      serverAssignments.push(req.url())
  })
  const field = (name: string) => page.locator(`#form-research_variable-${name} input`)
  await field("a").fill("3")
  await field("a").blur()
  await expect(field("b")).toHaveValue("6")
  await expect(field("c")).toHaveValue("7")
  await field("a").fill("4")
  await field("a").blur()
  await expect(field("b")).toHaveValue("8")
  await expect(field("c")).toHaveValue("9")
  // Failed calculation must not submit stale, previously valid derived values.
  await field("a").fill("13")
  await field("a").blur()
  await expect(page.getByText(/must be >= 0|greater than or equal|An upstream calculation failed/i).first()).toBeVisible()
  await page.getByRole("button", { name: "Submit", exact: true }).click()
  await expect(page.getByTestId("record-submission-errors")).toContainText("A calculation failed")
  await expect(field("c")).toHaveValue("9")
  await field("a").fill("4")
  await field("a").blur()
  await expect(field("b")).toHaveValue("8")
  await expect(field("c")).toHaveValue("9")
  expect(serverAssignments).toEqual([])
  // Recovery deliberately produces the same values retained before the error.
  // Those values alone cannot prove that the debounced calculation has finished.
  const calculationProgress = page.locator(".compact-progress")
  await expect(calculationProgress).toContainText("Completed")
  await expect(calculationProgress).toBeHidden()
  await page.getByRole("button", { name: "Submit", exact: true }).click()
  await page.getByRole("dialog").getByRole("button", { name: "Submit Record", exact: true }).click()
  await page.getByRole("dialog").getByRole("button", { name: "View saved Record", exact: true }).click()
  await expect(page).toHaveURL(/\/record\/[^/]+\/v1$/)
  await page.reload()
  await expect(field("b")).toHaveValue("8")
  await expect(field("c")).toHaveValue("9")
  expect(serverAssignments).toEqual([])

  // Actual published parser/runtime, inside Chromium, not mocked JS execution.
  const contracts = await page.evaluate(async (content) => {
    const url = "/src/views/project-protocols/modules/protocol/helpers/clientAssigners.ts"
    const { resolveProtocolAssigners, runProtocolClientAssigner } = await import(/* @vite-ignore */ url)
    const run = (source: string, values: Record<string, unknown>, readonly = false) => {
      const assigner = resolveProtocolAssigners(source).b
      return runProtocolClientAssigner(source, assigner, values, undefined, readonly)
    }
    const rejected = (callback: () => unknown) => {
      try {
        callback()
        return false
      }
      catch { return true }
    }
    return {
      manual: run(content.replaceAll("\"auto\"", "\"manual\""), { a: 2 }),
      first: run(content.replaceAll("\"auto\"", "\"auto_first\""), { a: 2 }),
      missing: rejected(() => run(content, {})),
      invalidInput: rejected(() => run(content, { a: -1 })),
      invalidOutput: rejected(() => run(content.replace("a * 2", "-1"), { a: 2 })),
      infinite: rejected(() => run(content.replace("a * 2", "a / 0"), { a: 2 })),
      readonly: rejected(() => run(content, { a: 2 }, true)),
      unsafe: rejected(() => run(content.replace("a * 2", "fetch(\"https://example.invalid\")"), { a: 2 })),
    }
  }, aimd)
  expect(contracts).toEqual({ manual: { b: 4 }, first: { b: 4 }, missing: true, invalidInput: true, invalidOutput: true, infinite: true, readonly: true, unsafe: true })

  await page.goto(`${path}/protocol`)
  for (const format of ["aira", "zip"]) {
    await page.getByRole("button", { name: "Download", exact: true }).click()
    const downloadPromise = page.waitForEvent("download")
    await page.getByText(format === "aira" ? "Airalogy archive (.aira, recommended)" : "Source package (.zip)", { exact: true }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toMatch(new RegExp(`\\.${format}$`))
    const stream = await download.createReadStream()
    const chunks: Buffer[] = []
    for await (const chunk of stream!) chunks.push(Buffer.from(chunk))
    const bytes = Buffer.concat(chunks)
    const files = unzipSync(bytes)
    expect(strFromU8(files["protocol.aimd"])).toBe(aimd)
    expect(Boolean(files["_airalogy_archive/manifest.json"])).toBe(format === "aira")
    const destinationResponse = await request.post(`${api}/projects`, { headers, data: {
      lab_id: fixtures.lab.id,
      uid: `${uid}_${format}`,
      name: `Synthetic ${format} restore`,
      type: 1,
    } })
    expect(destinationResponse.ok(), await destinationResponse.text()).toBeTruthy()
    const destination = await destinationResponse.json()
    const restoreUrl = format === "aira" ? `/projects/${destination.id}/aira/import` : "/protocols"
    const restored = await request.post(`${api}${restoreUrl}`, { headers, multipart: {
      project_id: destination.id,
      file: { name: `restored.${format}`, mimeType: format === "zip" ? "application/zip" : "application/octet-stream", buffer: bytes },
    } })
    expect(restored.ok(), await restored.text()).toBeTruthy()
    if (format === "aira")
      expect((await restored.json()).imported_protocol_count).toBe(1)
    await page.goto(`/labs/${fixtures.lab.uid}/projects/${destination.uid}/protocols/${protocol.uid}/add`)
    await field("a").fill("5")
    await field("a").blur()
    await expect(field("b")).toHaveValue("10")
    await expect(field("c")).toHaveValue("11")
    await page.goto(`${path}/protocol`)
  }
})

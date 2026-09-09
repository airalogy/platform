/* eslint-disable unicorn/prefer-dom-node-text-content -- Capture visible labels, never hidden descendant text. */
import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { join } from "node:path"
import { browserEngine, BrowserRuntime } from "./browser-runtime.mjs"
import { bytesDigest, canonical, checkKey, checkObject, checkText, digest, MAX_BYTES, validateBrowserEnvironment, validateLocator } from "./contract.mjs"
import { Evidence, readPrivateSelection } from "./evidence.mjs"
import { overlapsPrivate } from "./privacy.mjs"
import { validateSurveyReport } from "./survey-contract.mjs"

const selector = "button,input:not([type=hidden]),textarea,select,a[href],h1,h2,h3,h4,h5,h6,output,[role],[data-testid]"
const valueSelector = "input:not([type=button]):not([type=submit]):not([type=reset]),textarea,select,[contenteditable],[role=textbox],[role=searchbox],[role=combobox],[role=spinbutton],[role=checkbox],[role=radio],[role=switch]"
function locate(root, spec) {
  return spec.kind === "role" ? root.getByRole(spec.role, { name: spec.name, exact: true }) : root.getByTestId(spec.name)
}
function freeze(value) {
  if (value && typeof value === "object") {
    Object.values(value).forEach(freeze)
    Object.freeze(value)
  }
  return value
}
export async function previewSurvey(selection) {
  selection = JSON.parse(canonical(selection))
  if (Buffer.byteLength(canonical(selection)) > MAX_BYTES)
    throw new Error("Survey selection exceeds its limit")
  checkObject(selection, ["schema", "id", "target", "network", "blocked", "privacy", "limits", "capture_values"])
  if (selection.schema !== "airalogy.interface-survey-selection.v1" || typeof selection.capture_values !== "boolean" || selection.limits.max_steps !== 1)
    throw new Error("Survey requires explicit value consent and no action authority")
  checkKey(selection.id)
  checkObject(selection.target, ["application", "version", "title", "locale", "scope", "source"])
  for (const name of ["application", "version", "title", "locale"])
    checkText(selection.target[name])
  validateLocator(selection.target.scope)
  validateBrowserEnvironment(selection)
  if (selection.target.source.kind === "file" && bytesDigest(await readPrivateSelection(selection.target.source.path, 1048576)) !== selection.target.source.sha256)
    throw new Error("Selected survey HTML changed")
  const data = { schema: "airalogy.interface-survey-preview.v1", engine: browserEngine, definition: selection }
  return freeze({ ...data, sha256: digest(data) })
}

class BrowserSurvey extends BrowserRuntime {
  async capture() {
    this.phase = "survey_identity"
    this.remaining()
    const expected = this.definition.target.source.kind === "file" ? "about:blank" : this.definition.target.source.url
    if (this.page.url() !== expected || await this.page.title() !== this.definition.target.title || this.page.frames().length !== 1)
      throw new Error("Selected survey target changed")
    const scope = locate(this.page, this.definition.target.scope)
    if (await scope.count() !== 1 || !await scope.isVisible())
      throw new Error("Survey requires one visible selected scope")
    for (const spec of this.definition.blocked) {
      for (const element of await locate(this.page, spec).all()) {
        if (await element.isVisible())
          throw new Error("Blocking survey state detected")
      }
    }
    for (const role of ["dialog", "alertdialog"]) {
      if (await this.page.getByRole(role).count())
        throw new Error("Unexpected survey dialog")
    }
    const masks = [...this.definition.privacy.redact.map(spec => locate(this.page, spec)), this.page.locator("input[type=password],input[type=file]")]
    const masked = (await Promise.all(masks.map(item => item.elementHandles()))).flat()
    const valueMasked = this.definition.capture_values ? [] : await this.page.locator(valueSelector).elementHandles()
    const elements = await scope.locator(selector).elementHandles()
    try {
      if (elements.length > 200)
        throw new Error("Narrow the survey scope to at most 200 candidate elements")
      const controls = []
      let omittedPrivate = 0
      for (const element of elements) {
        this.remaining()
        if (!await element.isVisible())
          continue
        if (await element.evaluate(overlapsPrivate, masked)) {
          omittedPrivate += 1
          continue
        }
        // Name heuristics are hints only. A locator is retained only after the
        // browser's own role/name engine resolves to this exact, unique node.
        const hint = await element.evaluate((node, privacy) => {
          const tag = node.tagName.toLowerCase()
          const type = node.getAttribute("type")?.toLowerCase() || "text"
          let role = node.getAttribute("role")?.split(/\s+/)[0] || ""
          if (!role) {
            if (tag === "button" || (tag === "input" && ["button", "submit", "reset"].includes(type)))
              role = "button"
            else if (tag === "a")
              role = "link"
            else if (/^h[1-6]$/.test(tag))
              role = "heading"
            else if (tag === "output")
              role = "status"
            else if (tag === "select")
              role = node.multiple ? "listbox" : "combobox"
            else if (tag === "textarea")
              role = "textbox"
            else if (tag === "input")
              role = type === "number" ? "spinbutton" : ["checkbox", "radio"].includes(type) ? type : type === "search" ? "searchbox" : "textbox"
          }
          const contains = (ancestor, child) => {
            for (let current = child; current; current = current.assignedSlot || current.parentElement || current.getRootNode()?.host) {
              if (current === ancestor)
                return true
            }
            return false
          }
          const safeText = (item) => {
            if (!item || privacy.masked.some(mask => contains(mask, item)))
              return ""
            if (!privacy.masked.some(mask => contains(item, mask)))
              return item.innerText || ""
            // Preserve visible label text surrounding a masked input, without
            // reading the input's own text (including textarea defaults).
            return [...item.childNodes].map(child => child.nodeType === 3 ? child.textContent : child.nodeType === 1 && child.getClientRects().length ? safeText(child) : "").join("")
          }
          const labelled = (node.getAttribute("aria-labelledby") || "").split(/\s+/).map(id => safeText(document.getElementById(id))).join(" ").trim()
          const labels = node.labels ? [...node.labels].map(safeText).join(" ").trim() : ""
          const buttonInput = tag === "input" && ["button", "submit", "reset"].includes(type)
          const valueBearing = !buttonInput && (["input", "textarea", "select"].includes(tag) || node.isContentEditable || ["textbox", "searchbox", "combobox", "spinbutton", "checkbox", "radio", "switch"].includes(role))
          const name = node.getAttribute("aria-label") || labelled || labels || (buttonInput ? node.value : ["button", "link", "heading"].includes(role) && (!valueBearing || privacy.capture_values) ? safeText(node) : "") || node.getAttribute("title") || ""
          return { tag, type, role, value_bearing: valueBearing, name: name.trim(), test_id: node.getAttribute("data-testid") || "" }
        }, { masked: [...masked, ...valueMasked], capture_values: this.definition.capture_values })
        if (Buffer.byteLength(canonical(hint)) > 2048)
          throw new Error("Survey label exceeds its bound")
        let locator = null
        for (const candidate of [...(hint.test_id ? [{ kind: "test_id", name: hint.test_id }] : []), ...(hint.role && hint.name ? [{ kind: "role", role: hint.role, name: hint.name }] : [])]) {
          try {
            validateLocator(candidate)
          }
          catch { continue }
          const selected = locate(scope, candidate)
          if (await selected.count() !== 1)
            continue
          const match = await selected.elementHandle()
          try {
            if (match && await element.evaluate((node, matched) => node === matched, match)) {
              locator = candidate
              break
            }
          }
          finally { await match?.dispose() }
        }
        const readType = hint.tag === "input" && ["checkbox", "radio"].includes(hint.type) ? "checked" : ["input", "textarea", "select"].includes(hint.tag) && hint.value_bearing ? "value" : "text"
        const containsUnapprovedValue = valueMasked.length && await element.evaluate(overlapsPrivate, valueMasked)
        let read = containsUnapprovedValue || (hint.value_bearing && !this.definition.capture_values) ? null : readType
        let value = null
        if (read) {
          try {
            value = read === "value" ? await element.inputValue() : read === "checked" ? await element.isChecked() : await element.innerText()
          }
          catch { read = null }
        }
        if (Buffer.byteLength(canonical(value)) > 4096)
          throw new Error("Survey readback exceeds its bound")
        controls.push({ id: `observed.${controls.length + 1}`, label: hint.name || hint.test_id || hint.role || hint.tag, role: hint.role || "generic", locator, read, value, enabled: await element.isEnabled() })
        if (controls.length > 64)
          throw new Error("Narrow the survey scope to at most 64 visible controls")
      }
      this.remaining()
      if (this.page.url() !== expected || await this.page.title() !== this.definition.target.title)
        throw new Error("Survey target drifted during capture")
      const report = {
        schema: "airalogy.interface-survey.v1",
        id: randomUUID(),
        preview_digest: this.preview.sha256,
        target: { application: this.definition.target.application, version: this.definition.target.version, title: this.definition.target.title, locale: this.definition.target.locale, kind: this.definition.target.source.kind },
        capture_values: this.definition.capture_values,
        controls,
        omitted_private: omittedPrivate,
        limitations: ["Single client-reported snapshot; application version is operator-declared.", "No action, transition, physical safety or scientific result was tested.", "Name hints without a unique browser-verified locator require manual mapping."],
      }
      validateSurveyReport(report)
      let screenshot = null
      if (this.definition.privacy.screenshot) {
        const valueMasks = this.definition.capture_values ? [] : [this.page.locator(valueSelector)]
        const bytes = await scope.screenshot({ mask: [...masks, ...valueMasks], timeout: this.remaining(), animations: "disabled" })
        if (bytes.length > 2097152)
          throw new Error("Survey screenshot exceeds its bound")
        await this.evidence.write("survey.png", bytes)
        screenshot = { file: "survey.png", sha256: bytesDigest(bytes) }
      }
      await this.evidence.write("survey.json", Buffer.from(canonical(report)))
      await this.evidence.append("survey_captured", { report_digest: digest(report), screenshot, actions_executed: 0, hardware_qualified: false })
      return { report, screenshot }
    }
    finally {
      await Promise.all([...elements, ...masked, ...valueMasked].map(item => item.dispose()))
    }
  }
}

export async function runSurvey(selection, { confirmation, evidenceRoot }) {
  const preview = await previewSurvey(selection)
  if (confirmation !== preview.sha256)
    throw new Error("Confirm the exact survey target and capture policy before opening")
  const evidence = await Evidence.create(evidenceRoot, preview)
  const session = new BrowserSurvey(preview, evidence)
  try {
    await session.start()
    const { report } = await session.capture()
    return { evidence: evidence.directory, report_file: join(evidence.directory, "survey.json"), report_digest: digest(report), actions_executed: 0, hardware_qualified: false }
  }
  catch {
    await session.fail("Survey stopped; review target, privacy, bounds and private evidence")
    throw new Error(`Survey refused; inspect private evidence: ${evidence.directory}`)
  }
  finally { await session.close() }
}

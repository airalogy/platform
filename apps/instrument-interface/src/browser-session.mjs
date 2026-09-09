/* eslint-disable unicorn/prefer-dom-node-text-content -- Visible text, not hidden DOM text, is the approved readback. */
import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { createRequire } from "node:module"
import { isAbsolute } from "node:path"
import { performance } from "node:perf_hooks"
import { chromium } from "playwright"
import { bytesDigest, canonical, digest, validateDefinition, validatePlan } from "./contract.mjs"
import { Evidence, readPrivateSelection } from "./evidence.mjs"

const require = createRequire(import.meta.url)
const engine = { tool: require("../package.json").version, playwright: require("playwright/package.json").version }

function freeze(value) {
  if (value && typeof value === "object") {
    Object.values(value).forEach(freeze)
    Object.freeze(value)
  }
  return value
}

export async function previewInterface(definition, plan) {
  // Detach callers' mutable objects before approval or browser work.
  definition = validateDefinition(JSON.parse(canonical(definition)))
  plan = validatePlan(JSON.parse(canonical(plan)), definition)
  if (definition.target.source.kind === "file") {
    if (!isAbsolute(definition.target.source.path))
      throw new Error("Select an absolute HTML path")
    const bytes = await readPrivateSelection(definition.target.source.path, 1048576)
    if (bytesDigest(bytes) !== definition.target.source.sha256)
      throw new Error("Selected HTML bytes changed")
  }
  const selected = { schema: "airalogy.interface-preview.v1", engine, definition, plan }
  return freeze({ ...selected, sha256: digest(selected) })
}

function locate(root, spec) {
  return spec.kind === "role" ? root.getByRole(spec.role, { name: spec.name, exact: true }) : root.getByTestId(spec.name)
}

export class BrowserInterfaceSession {
  static async open({ definition, plan, confirmation, evidenceRoot }) {
    const preview = await previewInterface(definition, plan)
    if (confirmation !== preview.sha256)
      throw new Error("Confirm the exact current preview before opening the application")
    const evidence = await Evidence.create(evidenceRoot, preview)
    const session = new BrowserInterfaceSession(preview, evidence)
    try {
      await session.start()
      return session
    }
    catch {
      await session.fail("Application opening or initial observation failed")
      throw new Error(`Application opening refused; inspect private evidence: ${evidence.directory}`)
    }
  }

  constructor(preview, evidence) {
    this.preview = preview
    this.definition = preview.definition
    this.plan = preview.plan
    this.evidence = evidence
    this.sessionId = randomUUID()
    this.deadline = performance.now() + this.definition.limits.duration_seconds * 1000
    this.cursor = 0
    this.observationCount = 0
    this.closed = false
    this.busy = false
    this.fault = null
    this.lastObservation = null
    this.phase = "opening"
  }

  remaining() {
    const ms = Math.floor(this.deadline - performance.now())
    if (this.closed || this.fault || ms <= 0)
      throw new Error("Interface session stopped or authorization expired")
    return Math.min(ms, this.definition.limits.step_timeout_ms)
  }

  stop(reason) {
    this.fault ??= reason
  }

  async start() {
    await this.evidence.append("opening", { session_id: this.sessionId, confirmation: this.preview.sha256 })
    this.browser = await chromium.launch({ headless: true, chromiumSandbox: true, timeout: this.remaining() })
    this.timer = setTimeout(() => {
      this.stop("Session deadline reached")
      void this.context?.close().catch(() => {})
    }, Math.max(1, this.deadline - performance.now()))
    this.timer.unref()
    this.context = await this.browser.newContext({
      viewport: this.definition.limits.viewport,
      locale: this.definition.target.locale,
      acceptDownloads: false,
      serviceWorkers: "block",
      permissions: [],
    })
    this.context.setDefaultTimeout(this.definition.limits.step_timeout_ms)
    const counts = new Map()
    let receivedBytes = 0
    let navigations = 0
    await this.context.route("**/*", async (route) => {
      const request = route.request()
      const rule = this.definition.network.find(item => item.url === request.url() && item.method === request.method())
      const key = `${request.method()} ${request.url()}`
      const count = (counts.get(key) ?? 0) + 1
      const top = request.isNavigationRequest()
      const allowedNavigation = !top || (request.frame() === this.page?.mainFrame() && ++navigations === 1 && request.url() === this.definition.target.source.url)
      if (this.closed || this.fault || !rule || count > rule.max_requests || !allowedNavigation || request.redirectedFrom()) {
        this.stop("Blocked network request or navigation")
        await route.abort().catch(() => {})
        return
      }
      counts.set(key, count)
      try {
        // Browser route.continue follows redirects without re-entering the handler.
        // Fetch explicitly, with no browser cookies/credentials and no redirect following.
        const response = await fetch(rule.url, { method: rule.method, redirect: "manual", signal: AbortSignal.timeout(this.remaining()), headers: { Accept: request.headers().accept ?? "*/*" } })
        if (response.status >= 300 && response.status < 400) {
          await response.body?.cancel()
          throw new Error("Redirects are not authorized")
        }
        const chunks = []
        let size = 0
        if (response.body) {
          for await (const chunk of response.body) {
            size += chunk.length
            receivedBytes += chunk.length
            if (size > 2097152 || receivedBytes > 16777216)
              throw new Error("Application response exceeds the network budget")
            this.remaining()
            chunks.push(chunk)
          }
        }
        this.remaining()
        const headers = {}
        // Preserve restrictive document policies, not credentials or compressed lengths.
        for (const name of ["content-type", "content-security-policy", "x-content-type-options", "referrer-policy", "permissions-policy", "cross-origin-opener-policy", "cross-origin-embedder-policy"]) {
          if (response.headers.has(name))
            headers[name] = response.headers.get(name)
        }
        await route.fulfill({ status: response.status, headers, body: Buffer.concat(chunks) })
      }
      catch {
        this.stop("Application request failed, redirected or exceeded its budget")
        await route.abort().catch(() => {})
      }
    })
    await this.context.routeWebSocket("**/*", async (socket) => {
      this.stop("WebSocket connection is not authorized")
      await socket.close().catch(() => {})
    })
    this.context.on("page", (page) => {
      if (page !== this.page && this.page) {
        this.stop("Additional browser window detected")
        void page.close().catch(() => {})
      }
    })
    this.page = await this.context.newPage()
    this.page.on("dialog", async (dialog) => {
      this.stop("Unexpected JavaScript dialog")
      await dialog.dismiss().catch(() => {})
    })
    this.page.on("download", (download) => {
      this.stop("Downloads are not authorized")
      void download.cancel().catch(() => {})
    })
    this.page.on("frameattached", () => this.stop("Embedded frames are not authorized"))
    this.page.on("close", () => {
      if (!this.closed)
        this.stop("Application window closed")
    })
    const source = this.definition.target.source
    if (source.kind === "file") {
      const bytes = await readPrivateSelection(source.path, 1048576)
      if (bytesDigest(bytes) !== source.sha256)
        throw new Error("Selected HTML bytes changed after preview")
      // setContent does not give a document file:// access to sibling files.
      await this.page.setContent(bytes.toString("utf8"), { waitUntil: "load", timeout: this.remaining() })
    }
    else {
      await this.page.goto(source.url, { waitUntil: "load", timeout: this.remaining() })
    }
    await this.observe()
  }

  async unique(locator) {
    if (await locator.count() !== 1 || !await locator.isVisible())
      throw new Error("Expected exactly one visible selected control")
    return locator
  }

  async snapshot() {
    this.phase = "target"
    this.remaining()
    const expectedUrl = this.definition.target.source.kind === "file" ? "about:blank" : this.definition.target.source.url
    if (this.page.url() !== expectedUrl || await this.page.title() !== this.definition.target.title || this.page.frames().length !== 1)
      throw new Error("Application URL, title or frame identity changed")
    const scope = await this.unique(locate(this.page, this.definition.target.scope))
    this.phase = "version_identity"
    const identity = await this.unique(locate(scope, this.definition.target.identity.locator))
    if (await identity.innerText() !== this.definition.target.identity.text)
      throw new Error("Application version identity changed")
    this.phase = "blocking_controls"
    for (const spec of this.definition.blocked) {
      const blocked = locate(this.page, spec)
      for (const item of await blocked.all()) {
        if (await item.isVisible())
          throw new Error("Blocking interface state detected")
      }
    }
    for (const role of ["dialog", "alertdialog"]) {
      if (await this.page.getByRole(role).count())
        throw new Error("Unexpected visible dialog detected")
    }
    // Masks are page-scoped; no user-controlled JavaScript or selectors are executed.
    const masks = [...this.definition.privacy.redact.map(spec => locate(this.page, spec)), this.page.locator("input[type=\"password\"]")]
    const maskedHandles = (await Promise.all(masks.map(locator => locator.elementHandles()))).flat()
    const values = {}
    const enabled = {}
    try {
      for (const control of this.definition.controls) {
        this.phase = `control:${control.id}`
        const locator = await this.unique(locate(scope, control.locator))
        // Fixed trusted DOM predicate only. Never read a mask or its descendants/ancestors.
        const sensitive = await locator.evaluate((element, masked) => masked.some(item => item.contains(element) || element.contains(item)), maskedHandles)
        if (sensitive)
          throw new Error("Selected control overlaps private content")
        const value = control.read === "value" ? await locator.inputValue() : control.read === "checked" ? await locator.isChecked() : await locator.innerText()
        if (Buffer.byteLength(canonical(value)) > 4096)
          throw new Error("Control readback exceeds its evidence limit")
        values[control.id] = value
        enabled[control.id] = await locator.isEnabled()
      }
      this.phase = "state"
      const states = this.definition.states.filter(state => state.checks.every(check => values[check.control_id] === check.equals))
      if (states.length !== 1)
        throw new Error("Application state is unknown or ambiguous")
      this.remaining()
      const observation = { schema: "airalogy.interface-observation.v1", session_id: this.sessionId, preview: this.preview.sha256, target: { application: this.definition.target.application, version: this.definition.target.version }, state: states[0].id, values, enabled }
      return { observation, scope, masks, hasMasks: maskedHandles.length > 0 }
    }
    finally {
      await Promise.all(maskedHandles.map(handle => handle.dispose()))
    }
  }

  async saveObservation(snapshot) {
    this.phase = "evidence"
    if (this.observationCount >= this.definition.limits.max_steps * 2 + 1)
      throw new Error("Observation budget exhausted")
    const { observation, scope, masks, hasMasks } = snapshot
    let tree = null
    // ARIA serialization has no redaction API: omit it entirely when masks/passwords exist.
    if (!hasMasks) {
      tree = await scope.ariaSnapshot({ depth: 8, timeout: this.remaining() })
      if (Buffer.byteLength(tree) > 32768)
        tree = null
    }
    const stamp = String(this.evidence.sequence).padStart(4, "0")
    let screenshot = null
    if (this.definition.privacy.screenshot) {
      const bytes = await scope.screenshot({ mask: masks, timeout: this.remaining(), animations: "disabled" })
      if (bytes.length > 2097152)
        throw new Error("Screenshot exceeds its evidence limit")
      screenshot = { file: `${stamp}.png`, sha256: bytesDigest(bytes) }
      await this.evidence.write(screenshot.file, bytes)
    }
    this.remaining()
    await this.evidence.append("observation", { ...observation, sha256: digest(observation), accessibility: tree, screenshot })
    this.lastObservation = observation
    this.observationCount += 1
    return { ...observation, sha256: digest(observation) }
  }

  async observe() {
    if (this.busy)
      throw new Error("Concurrent interface operations are not allowed")
    this.busy = true
    try {
      return await this.saveObservation(await this.snapshot())
    }
    catch {
      await this.fail("Observation failed; state or authorization must be reviewed")
      throw new Error("Interface observation stopped; inspect private evidence")
    }
    finally {
      this.busy = false
    }
  }

  async step(expectedObservation) {
    if (this.busy)
      throw new Error("Concurrent interface operations are not allowed")
    this.busy = true
    let attempted = false
    try {
      const step = this.plan.steps[this.cursor]
      if (!step)
        throw new Error("No further step was confirmed")
      const before = await this.snapshot()
      this.phase = "precondition"
      if (expectedObservation !== digest(before.observation) || expectedObservation !== digest(this.lastObservation) || before.observation.state !== step.before)
        throw new Error("Observation changed since confirmation")
      if (!before.observation.enabled[step.control_id])
        throw new Error("Selected control is disabled")
      await this.evidence.append("step_intent", { index: this.cursor, step, before: expectedObservation })
      this.phase = "action"
      const control = this.definition.controls.find(item => item.id === step.control_id)
      const locator = await this.unique(locate(before.scope, control.locator))
      // Do not allow a late re-render to redirect the operation to another DOM node.
      const element = await locator.elementHandle()
      try {
        this.remaining()
        attempted = step.operation !== "read"
        if (step.operation === "fill")
          await element.fill(step.value, { timeout: this.remaining() })
        else if (step.operation === "click")
          await element.click({ timeout: this.remaining(), noWaitAfter: true })
      }
      finally {
        await element?.dispose()
      }
      const after = await this.snapshot()
      if (after.observation.state !== step.after || (step.operation === "fill" && after.observation.values[step.control_id] !== step.value))
        throw new Error("Postcondition or parameter readback failed")
      const saved = await this.saveObservation(after)
      await this.evidence.append("step_result", { index: this.cursor, after: saved.sha256, value: saved.values[step.control_id] })
      this.cursor += 1
      return saved
    }
    catch {
      await this.fail(attempted ? "Operation attempted; result uncertain. Do not replay before reconciliation." : "Step refused before operation; review changed state or authorization")
      throw new Error("Interface step stopped; no automatic retry or physical safe-stop claim")
    }
    finally {
      this.busy = false
    }
  }

  async fail(reason) {
    if (this.closed)
      return
    this.stop(reason)
    try {
      await this.evidence.append("stopped", { reason, fault: this.fault, phase: this.phase, next_step: this.cursor, physical_stop_confirmed: false })
    }
    finally {
      await this.close()
    }
  }

  async close() {
    if (this.closed)
      return
    this.closed = true
    clearTimeout(this.timer)
    await this.context?.close().catch(() => {})
    await this.browser?.close().catch(() => {})
    await this.evidence.append("closed", { completed_steps: this.cursor, planned_steps: this.plan.steps.length, physical_stop_confirmed: false })
  }
}

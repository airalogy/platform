import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { createRequire } from "node:module"
import { performance } from "node:perf_hooks"
import { chromium } from "playwright"
import { bytesDigest } from "./contract.mjs"
import { readPrivateSelection } from "./evidence.mjs"

const require = createRequire(import.meta.url)
export const browserEngine = Object.freeze({ tool: require("../package.json").version, playwright: require("playwright/package.json").version, ajv: require("ajv/package.json").version })

// Shared bounded launch/transport lifecycle. Subclasses validate their selected
// configuration and observations; this trusted local library is not an RPC API.
export class BrowserRuntime {
  constructor(preview, evidence) {
    this.preview = preview
    this.definition = preview.definition
    this.evidence = evidence
    this.sessionId = randomUUID()
    this.deadline = performance.now() + this.definition.limits.duration_seconds * 1000
    this.closed = false
    this.busy = false
    this.fault = null
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
    this.browser = await chromium.launch({ headless: this.headless !== false, chromiumSandbox: true, timeout: this.remaining(), ...(this.browserExecutable ? { executablePath: this.browserExecutable } : {}) })
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
  }

  async fail(reason) {
    if (this.closed)
      return
    this.stop(reason)
    try {
      await this.evidence.append("stopped", { reason, fault: this.fault, phase: this.phase, next_step: this.cursor ?? null, physical_stop_confirmed: false })
    }
    finally {
      await this.close()
    }
  }

  closeSummary() {
    return {}
  }

  async close() {
    if (this.closed)
      return
    this.closed = true
    clearTimeout(this.timer)
    await this.context?.close().catch(() => {})
    await this.browser?.close().catch(() => {})
    await this.evidence.append("closed", { ...this.closeSummary(), physical_stop_confirmed: false })
  }
}

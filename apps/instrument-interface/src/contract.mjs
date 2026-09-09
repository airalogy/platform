/* eslint-disable no-control-regex -- Reject control characters in selected interface strings. */
import { Buffer } from "node:buffer"
import { createHash } from "node:crypto"

export const SCHEMA = "airalogy.browser-interface.v1"
export const MAX_BYTES = 131072
const identifier = /^[A-Z][\w.-]{0,95}$/i
const hash = /^[a-f0-9]{64}$/
const roles = new Set(["main", "region", "heading", "button", "link", "textbox", "spinbutton", "combobox", "checkbox", "radio", "switch", "status", "alert", "alertdialog", "dialog", "tab", "tabpanel", "menuitem", "table", "cell", "row", "list", "listitem", "group", "generic"])

export function canonical(value) {
  function sorted(item, depth = 0) {
    if (depth > 32)
      throw new Error("Interface JSON is nested too deeply")
    if (item === null || typeof item === "string" || typeof item === "boolean")
      return item
    if (typeof item === "number" && Number.isFinite(item))
      return item
    if (Array.isArray(item))
      return item.map(child => sorted(child, depth + 1))
    if (item && Object.getPrototypeOf(item) === Object.prototype)
      return Object.fromEntries(Object.keys(item).sort().map(key => [key, sorted(item[key], depth + 1)]))
    throw new Error("Expected finite plain JSON")
  }
  return JSON.stringify(sorted(value))
}
export const digest = value => createHash("sha256").update(canonical(value)).digest("hex")
export const bytesDigest = value => createHash("sha256").update(value).digest("hex")

function object(value, required, optional = []) {
  if (!value || Object.getPrototypeOf(value) !== Object.prototype || required.some(key => !(key in value)) || Object.keys(value).some(key => ![...required, ...optional].includes(key)))
    throw new Error("Unexpected or missing interface fields")
}
function text(value, limit = 512, empty = false) {
  if (typeof value !== "string" || (!empty && !value.trim()) || Buffer.byteLength(value) > limit || /[\u0000-\u0008\v\f\u000E-\u001F]/u.test(value))
    throw new Error("Invalid bounded interface text")
  return value
}
function list(value, maximum, minimum = 0) {
  if (!Array.isArray(value) || value.length > maximum || value.length < minimum)
    throw new Error("Invalid bounded interface list")
  return value
}
function integer(value, low, high) {
  if (!Number.isInteger(value) || value < low || value > high)
    throw new Error("Interface limit is outside supported bounds")
}
function key(value) {
  if (typeof value !== "string" || !identifier.test(value))
    throw new Error("Invalid interface identifier")
}
function scalar(value) {
  if (value !== null && !["boolean", "number", "string"].includes(typeof value))
    throw new Error("Interface values must be literal scalars")
  if (Buffer.byteLength(canonical(value)) > 4096)
    throw new Error("Interface value exceeds its limit")
}

export function validateLocator(value) {
  object(value, ["kind", "name"], ["role"])
  text(value.name, 512, value.kind === "role")
  if (value.kind === "role") {
    if (!roles.has(value.role))
      throw new Error("Unsupported semantic role")
  }
  else if (value.kind !== "test_id" || "role" in value) {
    throw new Error("Use exact accessible names or test IDs, not arbitrary selectors")
  }
  return value
}

export function exactUrl(value) {
  text(value, 2048)
  const url = new URL(value)
  if (url.username || url.password || url.hash || url.href !== value || !["https:", "http:"].includes(url.protocol))
    throw new Error("Use an exact credential-free HTTP(S) application URL")
  if (url.protocol === "http:" && !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname))
    throw new Error("Live applications require HTTPS outside loopback")
  return url
}

export function validateDefinition(value) {
  if (Buffer.byteLength(canonical(value)) > MAX_BYTES)
    throw new Error("Interface definition exceeds 128 KiB")
  object(value, ["schema", "id", "target", "network", "controls", "states", "blocked", "privacy", "limits"])
  if (value.schema !== SCHEMA)
    throw new Error("Unknown interface schema")
  key(value.id)
  const target = value.target
  object(target, ["application", "version", "title", "locale", "scope", "source", "identity"])
  for (const name of ["application", "version", "title", "locale"])
    text(target[name])
  validateLocator(target.scope)
  object(target.identity, ["locator", "text"])
  validateLocator(target.identity.locator)
  text(target.identity.text)
  if (target.source?.kind === "file") {
    object(target.source, ["kind", "path", "sha256"])
    text(target.source.path, 4096)
    if (typeof target.source.sha256 !== "string" || !hash.test(target.source.sha256))
      throw new Error("Pin the explicitly selected HTML bytes")
  }
  else {
    object(target.source, ["kind", "url"])
    if (target.source.kind !== "url")
      throw new Error("Select an HTML file or exact application URL")
    exactUrl(target.source.url)
  }
  const requests = new Set()
  for (const rule of list(value.network, 32)) {
    object(rule, ["url", "method", "max_requests"])
    const url = exactUrl(rule.url)
    if (target.source.kind !== "url" || url.origin !== exactUrl(target.source.url).origin || !["GET", "HEAD"].includes(rule.method) || requests.has(`${rule.method} ${rule.url}`))
      throw new Error("Authorize unique same-origin read requests only; local HTML has no network")
    integer(rule.max_requests, 1, 100)
    requests.add(`${rule.method} ${rule.url}`)
  }
  if (target.source.kind === "url" && !requests.has(`GET ${target.source.url}`))
    throw new Error("Explicitly authorize the selected application's initial GET")
  const controls = new Map()
  const locators = new Set()
  for (const control of list(value.controls, 64, 1)) {
    object(control, ["id", "locator", "read", "operations"])
    key(control.id)
    validateLocator(control.locator)
    const signature = canonical(control.locator)
    if (controls.has(control.id) || locators.has(signature) || !["text", "value", "checked"].includes(control.read))
      throw new Error("Controls must have unique identities and supported readback")
    const ops = list(control.operations, 3, 1)
    if (new Set(ops).size !== ops.length || ops.some(op => !["read", "fill", "click"].includes(op)) || (ops.includes("fill") && control.read !== "value"))
      throw new Error("Declare only read/fill/click with matching readback")
    locators.add(signature)
    controls.set(control.id, control)
  }
  const states = new Set()
  for (const state of list(value.states, 16, 1)) {
    object(state, ["id", "checks"])
    key(state.id)
    if (states.has(state.id))
      throw new Error("State IDs must be unique")
    states.add(state.id)
    for (const check of list(state.checks, 16, 1)) {
      object(check, ["control_id", "equals"])
      if (!controls.has(check.control_id))
        throw new Error("State refers to an undeclared control")
      scalar(check.equals)
    }
  }
  list(value.blocked, 16).forEach(validateLocator)
  object(value.privacy, ["redact", "screenshot"])
  list(value.privacy.redact, 16).forEach(validateLocator)
  if (typeof value.privacy.screenshot !== "boolean")
    throw new Error("Screenshot consent must be explicit")
  object(value.limits, ["duration_seconds", "max_steps", "step_timeout_ms", "viewport"])
  integer(value.limits.duration_seconds, 1, 900)
  integer(value.limits.max_steps, 1, 40)
  integer(value.limits.step_timeout_ms, 100, 10000)
  object(value.limits.viewport, ["width", "height"])
  integer(value.limits.viewport.width, 320, 1920)
  integer(value.limits.viewport.height, 240, 1080)
  return value
}

export function validateStep(value, definition) {
  object(value, ["operation", "control_id", "before", "after"], ["value"])
  const control = definition.controls.find(item => item.id === value.control_id)
  if (!control || !control.operations.includes(value.operation) || !definition.states.some(item => item.id === value.before) || !definition.states.some(item => item.id === value.after))
    throw new Error("Step is outside the selected interface contract")
  if (value.operation === "fill") {
    if (typeof value.value !== "string")
      throw new Error("Fill requires an explicit literal string")
    scalar(value.value)
  }
  else if ("value" in value) {
    throw new Error("Only fill accepts a value")
  }
  if (["read", "fill"].includes(value.operation) && value.before !== value.after)
    throw new Error("Read and parameter entry cannot declare a state transition")
  return value
}

export function validatePlan(value, definition) {
  object(value, ["schema", "steps"])
  if (value.schema !== "airalogy.interface-plan.v1")
    throw new Error("Unknown replay plan")
  list(value.steps, definition.limits.max_steps).forEach(step => validateStep(step, definition))
  if (definition.target.source.kind === "url" && value.steps.some(step => step.operation !== "read"))
    throw new Error("Live URL sessions are observation-only; equipment-changing UI requires a separately qualified Gateway adapter")
  for (let i = 1; i < value.steps.length; i++) {
    if (value.steps[i].before !== value.steps[i - 1].after)
      throw new Error("Replay steps must form a continuous state sequence")
  }
  return value
}

/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import { compileTemplate, parse } from "@vue/compiler-sfc"
import ts from "typescript"

test("Protocol export keeps explicit version, defaults to aira and supports ZIP", async () => {
  const source = readFileSync(new URL("../src/service/api/protocol-export.ts", import.meta.url), "utf8")
  const calls = []
  const links = []
  globalThis.__exportCalls = calls
  const oldDocument = globalThis.document
  const oldTimeout = globalThis.setTimeout
  globalThis.document = { createElement: () => {
    const link = { click() {} }
    links.push(link)
    return link
  } }
  globalThis.setTimeout = callback => callback()
  try {
    const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText.replace('import { request } from "../request";', 'const request = async config => { globalThis.__exportCalls.push(config); return { data: new Blob(["archive"]) } };')
    const api = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`)
    await api.downloadProtocolExport("p1", "0.1.0")
    await api.downloadProtocolExport("p1", "0.2.0", "zip")
    assert.equal(calls[0].url, "/protocols/p1/export")
    assert.deepEqual(calls.map(c => c.params), [{ version: "0.1.0", format: "aira" }, { version: "0.2.0", format: "zip" }])
    assert.deepEqual(links.map(l => l.download), ["protocol-p1-v0.1.0.aira", "protocol-p1-v0.2.0.zip"])
  }
  finally {
    globalThis.document = oldDocument
    globalThis.setTimeout = oldTimeout
    delete globalThis.__exportCalls
  }
})

test("shared download menu compiles with both explicit choices", () => {
  const { descriptor } = parse(readFileSync(new URL("../src/components/protocol/protocol-download.vue", import.meta.url), "utf8"))
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: "protocol-download.vue", id: "download" }).errors, [])
  assert.match(descriptor.scriptSetup.content, /exportAira/)
  assert.match(descriptor.scriptSetup.content, /exportZip/)
  assert.match(descriptor.template.content, /:loading="loading"/)
})

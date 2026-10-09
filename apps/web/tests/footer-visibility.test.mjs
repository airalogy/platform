/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import { compileTemplate, parse } from "@vue/compiler-sfc"
import ts from "typescript"
import { createSSRApp, defineComponent, h } from "vue"
import { renderToString } from "vue/server-renderer"

const read = path => readFileSync(new URL(path, import.meta.url), "utf8")
const { descriptor } = parse(read("../src/layouts/global-layout/index.vue"))
const compiled = compileTemplate({ source: descriptor.template.content, filename: "global-layout.vue", id: "footer-regression" })
assert.deepEqual(compiled.errors, [])
const { render } = await import(`data:text/javascript;base64,${Buffer.from(compiled.code.replaceAll('from "vue"', `from "${import.meta.resolve("vue")}"`)).toString("base64")}`)

// Render the actual application-shell template. The layout stub exercises its
// footerVisible/fullContent contract without loading unrelated UI plugins.
async function renderShell({ visible = true, hideFooter = false, fullContent = false } = {}) {
  return renderToString(createSSRApp({
    components: {
      AIRALayout: defineComponent({
        props: ["footerVisible", "fullContent"],
        setup: (props, { slots }) => () => h("div", props.footerVisible && !props.fullContent ? slots.footer?.() : null),
      }),
      GlobalHeader: { render: () => h("header") },
      GlobalContent: { render: () => h("main") },
      GlobalFooter: { render: () => h("footer", "Company and configured compliance information") },
    },
    data: () => ({
      props: {},
      route: { meta: { hideFooter } },
      appStore: { fullContent },
      themeStore: { header: {}, tab: {}, sider: {}, content: {}, footer: { visible } },
      wrapperRef: null,
      layoutClass: "",
      layoutMode: "vertical",
      layoutScrollMode: "wrapper",
      LAYOUT_SCROLL_EL_ID: "layout-scroll",
      contentOverflowClass: "",
      siderVisible: false,
      siderWidth: 0,
      siderCollapsedWidth: 0,
      contentMaxWidth: 1800,
      shellMaxWidth: 1800,
      headerProps: {},
      popoverComponent: null,
      popoverFloating: null,
      floatingStyles: {},
    }),
    render,
  }))
}

test("ordinary pages retain the footer even with an old hidden-footer cache", async () => {
  for (const visible of [false, true, undefined])
    assert.match(await renderShell({ visible }), /<footer\b[^>]*>Company and configured compliance information<\/footer>/)
})

test("focus routes hide only their own footer; returning restores it", async () => {
  assert.doesNotMatch(await renderShell({ hideFooter: true }), /<footer\b/)
  assert.match(await renderShell({ visible: false }), /<footer\b/)
})

test("explicit full-content mode still hides layout chrome", async () => {
  assert.doesNotMatch(await renderShell({ fullContent: true }), /<footer\b/)
})

test("Record entry, workflow entry and report declare route-local footer suppression", async () => {
  const source = ts.transpileModule(read("../src/router/routes/modules/protocol-record.ts"), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  }).outputText
  const { protocolRecordRoute } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`)
  assert.equal(protocolRecordRoute.meta.hideFooter, undefined)
  assert.deepEqual(protocolRecordRoute.children.map(route => [route.name, route.meta.hideFooter]), [
    ["add-protocol-record", true],
    ["add-protocol-record-from-workflow", true],
    ["protocol-record-report", true],
  ])
})

test("Record components cannot persist temporary footer visibility in the shared theme", () => {
  for (const path of ["protocol-add-record.vue", "record-report.vue"])
    assert.doesNotMatch(read(`../src/views/project-protocols/${path}`), /themeStore\.footer/)
})

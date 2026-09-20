/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { Buffer } from "node:buffer"
import { readFileSync } from "node:fs"
import test from "node:test"
import ts from "typescript"

// Exercise the real pure declarations without mounting the surrounding Vue
// composables or importing their browser-only icon and authentication modules.
function declarations(path, names, vue = false) {
  let source = readFileSync(new URL(path, import.meta.url), "utf8")
  if (vue)
    source = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1]
  const file = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const found = file.statements.filter((statement) => {
    if (ts.isFunctionDeclaration(statement))
      return names.includes(statement.name?.text)
    return ts.isVariableStatement(statement) && statement.declarationList.declarations.some(declaration => names.includes(declaration.name.getText(file)))
  })
  assert.equal(found.length, names.length, `Missing production declarations in ${path}`)
  return found.map(statement => statement.getText(file)).join("\n")
}

const source = [
  declarations("../../../packages/shared/src/utils/uri.ts", ["getFileExtensionFromBasename"]),
  declarations("../../../packages/shared/src/utils/file/fileType.ts", ["UPLOAD_FILE_TYPES", "isUploadFileType", "unifiedFileTypes", "getFileType", "getBaseUploadProps"]),
  declarations("../node_modules/@airalogy/aimd-core/src/utils/schema.ts", ["schemaToInputType"]),
  declarations("../src/components/custom/aimd/composables/useAIMDHelpers.ts", ["getInputType", "getSchemasFromAnyOf", "getFirstTypeFromAnyOf"]),
  `export function uploadAccept(schema) {
    const ajvInfo = { value: { schema } }
    const rawType = { value: getInputType(schema) }
    const computed = getter => getter()
    ${declarations("../src/views/project-protocols/modules/protocol/components/inputs/file-input.vue", ["acceptType"], true)}
    return acceptType
  }`,
].join("\n")
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true })
assert.deepEqual(compiled.diagnostics, [])
const { getInputType, getFileType, isUploadFileType, uploadAccept } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`)

test("explicit JSON, text and unknown FileIds use a file widget, not a text editor", () => {
  assert.equal(getFileType("json", true), "code")
  assert.equal(getFileType("txt", true), "text")
  for (const key of ["airalogy_type", "airalogy_built_in_type"]) {
    for (const extension of ["json", "txt", "exe", "synthetic-unrecognized", undefined]) {
      const schema = { type: "string", [key]: "FileId", file_extension: extension }
      const before = structuredClone(schema)
      assert.equal(getInputType(schema), "file")
      assert.equal(isUploadFileType(getInputType(schema)), true)
      assert.deepEqual(schema, before)
    }
  }
  for (const extension of ["csv", "pdf", "png"])
    assert.equal(getInputType({ type: "string", airalogy_type: "FileId", file_extension: extension }), getFileType(extension, true))
})

test("nullable FileId alternatives keep the same safe widget dispatch", () => {
  for (const key of ["airalogy_type", "airalogy_built_in_type"]) {
    for (const extension of ["json", "txt", "synthetic-unrecognized"]) {
      const schema = { anyOf: [{ type: "null" }, { type: "string", [key]: "FileId", file_extension: extension }] }
      const before = structuredClone(schema)
      assert.equal(getInputType(schema), "file")
      assert.deepEqual(schema, before)
    }
  }
})

test("ordinary string, text and code fields are not promoted to file inputs", () => {
  for (const schema of [{ type: "string" }, { type: "text" }, { type: "string", file_extension: "json" }, { type: "string", input_type: "text" }, { type: "string", input_type: "code" }, { anyOf: [{ type: "null" }, { type: "string" }] }])
    assert.equal(isUploadFileType(getInputType(schema)), false)
  assert.equal(getInputType({ type: "string" }), "textarea")
  assert.equal(getInputType({ type: "text" }), "text")
  assert.equal(getInputType({ type: "number" }), "float")
})

test("generic FileId widget dispatch retains the exact schema upload extension", () => {
  for (const extension of ["json", ".json", "txt", "synthetic-unrecognized"]) {
    const schema = { type: "string", airalogy_type: "FileId", file_extension: extension }
    assert.equal(getInputType(schema), "file")
    assert.equal(uploadAccept(schema), extension.startsWith(".") ? extension : `.${extension}`)
    assert.equal(schema.file_extension, extension)
  }
})

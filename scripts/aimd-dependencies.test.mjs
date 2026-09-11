/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { existsSync, readdirSync, readFileSync } from "node:fs"
import path from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const names = ["@airalogy/aimd-core", "@airalogy/aimd-editor", "@airalogy/aimd-renderer"]
const readJson = file => JSON.parse(readFileSync(path.join(root, file), "utf8"))

test("shared AIMD dependencies have a single exact release pin in the workspace catalog", () => {
  const workspace = readFileSync(path.join(root, "pnpm-workspace.yaml"), "utf8")
  const catalog = workspace.split(/^catalog:\s*$/m)[1]?.split(/^\S/m)[0]
  assert.ok(catalog, "The default workspace catalog must exist")
  for (const name of names) {
    const entries = catalog.split("\n").filter(line => line.startsWith(`  '${name}':`))
    assert.equal(entries.length, 1, `${name} must have exactly one catalog entry`)
    assert.match(entries[0].split(": ")[1], /^\d+\.\d+\.\d+$/, `${name} must pin a stable release`)
  }
})

test("every direct AIMD consumer uses the shared catalog instead of independent versions", () => {
  const consumers = new Set()
  for (const group of ["apps", "packages"]) {
    for (const entry of readdirSync(path.join(root, group), { withFileTypes: true })) {
      const file = `${group}/${entry.name}/package.json`
      if (!entry.isDirectory() || !existsSync(path.join(root, file)))
        continue
      const manifest = readJson(file)
      for (const section of ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]) {
        for (const name of names) {
          if (manifest[section]?.[name] === undefined)
            continue
          consumers.add(name)
          assert.equal(manifest[section][name], "catalog:", `${file} ${section}.${name} must use catalog:`)
        }
      }
    }
  }
  assert.equal(consumers.size, names.length)
})

test("native Renderer controls no longer rely on a Platform patch", () => {
  const patches = readJson("package.json").pnpm?.patchedDependencies || {}
  assert.ok(Object.keys(patches).every(name => !name.startsWith("@airalogy/aimd-renderer@")))
  assert.ok(readdirSync(path.join(root, "patches")).every(name => !name.startsWith("@airalogy__aimd-renderer@")))
})

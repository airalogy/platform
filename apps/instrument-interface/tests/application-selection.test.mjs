/* eslint-disable test/no-import-node-test */
import assert from "node:assert/strict"
import { execFile } from "node:child_process"
import { mkdir, mkdtemp, readFile, realpath, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { promisify } from "node:util"
import { resolveApplicationSelection, selectedMetadata } from "../src/application-selection.mjs"
import { selectionShape, validateApplicationAnalysis, validateApplicationCandidates } from "../src/application-selection-contract.mjs"
import { canonical, digest } from "../src/contract.mjs"
import { prepareNativeDiscovery, runNativeDiscovery } from "../src/native-discovery.mjs"

const exec = promisify(execFile)
const cli = process.env.AIRALOGY_TEST_NATIVE_CLI || fileURLToPath(new URL("../src/native-cli.mjs", import.meta.url))

async function fixture() {
  const report = JSON.parse(await readFile(new URL("./fixtures/application-candidates.json", import.meta.url), "utf8"))
  const analysis = { summary: "Possible reader software, not confirmed identity", recommendations: [{ candidate_id: "candidate_1", rationale: "The declared name refers to a reader", evidence_fields: ["name"] }], limitations: ["Metadata only, no verified capabilities"], missing_information: ["Confirm vendor and exact instrument model"] }
  return { report, analysis }
}

test("selected metadata excludes local paths, unselected software and discovery internals", async () => {
  const { report } = await fixture()
  const inventory = { directory: { path: "/private/synthetic/applications" }, applications: [{ bundle_path: "/private/synthetic/Reader.app", directory_name: "Private name.app", declared: report.candidates[0] }, { declared: { name: "UNSELECTED_SOFTWARE" } }] }
  const selected = selectedMetadata(inventory, [1], report.id)
  validateApplicationCandidates(selected)
  const encoded = canonical(selected)
  for (const excluded of ["/private/", "bundle_path", "directory_name", "UNSELECTED_SOFTWARE"])
    assert.ok(!encoded.includes(excluded))
  assert.equal(selected.source_digest, digest(inventory))
  for (const indices of [[], [0], [3], [1, 1], [true], ["1"]])
    assert.throws(() => selectedMetadata(inventory, indices, report.id))
})

test("candidate reports and recommendations reject invented paths, IDs, evidence and authority", async () => {
  const { report, analysis } = await fixture()
  validateApplicationCandidates(report)
  validateApplicationAnalysis(analysis, report)
  for (const mutate of [
    item => item.bundle_path = "/private/app",
    item => item.candidates[0].bundle_path = "/private/app",
    item => item.candidates.push(item.candidates[0]),
    item => item.candidates[0].name = `aigw_${"A".repeat(43)}`,
    item => item.candidates[0].name = "界".repeat(200),
    item => item.candidates[0].info_sha256 = null,
  ]) {
    const bad = structuredClone(report)
    mutate(bad)
    assert.throws(() => validateApplicationCandidates(bad))
  }
  for (const mutate of [
    item => item.recommendations[0].candidate_id = "candidate_9",
    item => item.recommendations[0].evidence_fields = ["display_name"],
    item => item.recommendations[0].evidence_fields = ["name", "name"],
    item => item.recommendations.push(item.recommendations[0]),
    item => item.actions = ["launch"],
    item => item.recommendations[0].path = "/Applications/Other.app",
  ]) {
    const bad = structuredClone(analysis)
    mutate(bad)
    assert.throws(() => validateApplicationAnalysis(bad, report))
  }
  validateApplicationAnalysis({ ...analysis, recommendations: [] }, report)
  assert.throws(() => validateApplicationAnalysis({ ...analysis, recommendations: [], missing_information: [] }, report))
})

test("candidate analysis cannot masquerade as a runnable survey or startup export", async () => {
  const { report, analysis } = await fixture()
  const exported = { schema: "airalogy.application-selection-export.v1", session_id: report.id, turn_id: report.id, capture_digest: digest(report), analysis }
  selectionShape("export", exported)
  assert.throws(() => selectionShape("export", { ...exported, schema: "airalogy.survey-analysis-export.v1" }))
  assert.throws(() => selectionShape("export", { ...exported, launch_approved: true }))
})

test("private selection mapping refuses drift and mismatched AI suggestions before identity inspection", { skip: process.platform !== "darwin" }, async () => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "airalogy-selection-")))
  const applications = join(root, "apps")
  const contents = join(applications, "Synthetic.app", "Contents")
  await mkdir(contents, { recursive: true, mode: 0o700 })
  await writeFile(join(contents, "Info.plist"), canonical({ CFBundlePackageType: "APPL", CFBundleName: "Synthetic Reader", CFBundleIdentifier: "org.airalogy.synthetic", CFBundleShortVersionString: "1.0" }), { mode: 0o600 })
  const discovery = await prepareNativeDiscovery({ directory: applications, workspace: root })
  await runNativeDiscovery(discovery.request_file, discovery.preview_digest)
  const { stdout } = await exec(process.execPath, [cli, "prepare-selection", "--request", discovery.request_file, "--indices", "1", "--workspace", root], { timeout: 10000 })
  const prepared = JSON.parse(stdout)
  const report = JSON.parse(await readFile(prepared.candidates_file, "utf8"))
  assert.equal(prepared.uploaded, false)
  assert.equal(prepared.model_called, false)
  assert.ok(!canonical(report).includes(root))
  assert.ok(!stdout.includes("Synthetic Reader"))
  await assert.rejects(exec(process.execPath, [cli, "prepare-selection", "--request", discovery.request_file, "--indices", "1,1", "--workspace", root], { timeout: 10000 }))
  const options = { selectionFile: prepared.selection_file, candidateId: "candidate_2", buildFile: "/not/a/trusted/build" }
  await assert.rejects(resolveApplicationSelection(options), /known candidate/)
  const { analysis } = await fixture()
  const exported = { schema: "airalogy.application-selection-export.v1", session_id: report.id, turn_id: report.id, capture_digest: "c".repeat(64), analysis }
  const analysisFile = join(root, "analysis.json")
  await writeFile(analysisFile, canonical(exported), { mode: 0o600 })
  await assert.rejects(resolveApplicationSelection({ ...options, candidateId: "candidate_1", analysisFile }), /different selected metadata/)
  await writeFile(analysisFile, canonical({ ...exported, capture_digest: digest(report), analysis: { ...analysis, recommendations: [] } }))
  await assert.rejects(resolveApplicationSelection({ ...options, candidateId: "candidate_1", analysisFile }), /not recommended/)
  await writeFile(prepared.candidates_file, canonical({ ...report, source_digest: "e".repeat(64) }))
  await assert.rejects(resolveApplicationSelection({ ...options, candidateId: "candidate_1" }), /metadata changed/)
})

import type { APIRequestContext } from "@playwright/test"
import { execFileSync } from "node:child_process"
import { createHash, randomBytes, randomUUID } from "node:crypto"
import { mkdir, readFile, writeFile } from "node:fs/promises"
import path from "node:path"
import { expect } from "@playwright/test"
import { loadFixtures } from "./fixtures"

// Disposable synthetic software only. No equipment, vendor software or laboratory files.
// Uses the real package, installation, isolated SDK process, HTTP and object store.
export async function deliverSyntheticFile(request: APIRequestContext, directory: string) {
  const fixtures = await loadFixtures()
  const api = process.env.E2E_API_URL || "http://127.0.0.1:4100"
  const login = await request.post(`${api}/signin_by_email`, { data: { email: "dev.owner@airalogy.dev", password: "AiralogyDev123!" } })
  const headers = { "Auth-Token": (await login.json()).token }
  async function call(route: string, data?: unknown, method = "POST") {
    const response = await request.fetch(api + route, { method, headers, data })
    expect(response.ok(), `${route}: ${await response.text()}`).toBeTruthy()
    return response.json()
  }
  async function confirm(route: string, data: Record<string, unknown>) {
    const preview = await call(`${route}/preview`, data)
    return call(route, { ...data, preview_digest: preview.preview_digest })
  }
  const suffix = randomUUID().replaceAll("-", "")
  const base = `/labs/${fixtures.lab.id}/resource-library`
  const definitions = await call(`${base}/definition-versions`, undefined, "GET")
  const definition = definitions.items.find((item: { protocol_uid: string }) => item.protocol_uid === "plasmid_resource_definition_en")
  const kind = await call(`${base}/types`, { protocol_version_id: definition.id, code: `file_${suffix}`, name: "Synthetic file equipment", capabilities: { booking: true }, booking_policy: "auto" })
  const resource = await call(`${base}/resources`, { resource_type_id: kind.id, name: `Synthetic file reader ${suffix}`, code: suffix, visibility: "lab", data: { construct_name: "Synthetic", aliases: null, backbone: null, sequence: null, sequence_file: null, resistance_markers: null, host_species: null, copy_number: null, external_source: null, features: [] } })
  const gateway = (await confirm("/research-instrument-gateways", { lab_id: fixtures.lab.id, name: `Synthetic file station ${suffix}`, enabled: false })).gateway
  const pairing = await confirm("/instrument-pairings", { gateway_id: gateway.id, expected_revision: gateway.revision, reason: "Synthetic file test pairing" })
  const token = `aigw_${randomBytes(32).toString("base64url")}`
  await call("/instrument-pairings/claim", { code: pairing.code, gateway_id: gateway.id, lab_id: fixtures.lab.id, client_name: "Synthetic station", credential_digest: createHash("sha256").update(token).digest("hex"), credential_hint: token.slice(-8) })
  const pairPreview = await call(`/instrument-pairings/${pairing.pairing.id}/preview`, {})
  await call(`/instrument-pairings/${pairing.pairing.id}/confirm`, { preview_digest: pairPreview.preview_digest })
  const env = { ...process.env, PYTHONPATH: "apps/instrument-gateway/src:apps/instrument-gateway/tests" }
  function python(args: string[]) {
    return execFileSync("python3", args, { env, encoding: "utf8", timeout: 45000 })
  }
  python(["-c", "import sys; from pathlib import Path; from managed_fixture import package; Path(sys.argv[1]).write_bytes(package(physical_policy=True, file_outputs=True))", path.join(directory, "synthetic.zip")])
  const raw = await readFile(path.join(directory, "synthetic.zip"))
  const upload = { headers: { ...headers, "Content-Type": "application/zip" }, params: { lab_id: fixtures.lab.id, request_id: randomUUID() }, data: raw }
  const preview = await request.post(`${api}/instrument-adapter-packages/preview`, upload)
  expect(preview.ok(), await preview.text()).toBeTruthy()
  const imported = await request.post(`${api}/instrument-adapter-packages`, { ...upload, headers: { ...upload.headers, "X-Airalogy-Preview-Digest": (await preview.json()).preview_digest } })
  expect(imported.ok(), await imported.text()).toBeTruthy()
  const release = await imported.json()
  if (release.state === "imported")
    await confirm(`/instrument-adapter-packages/${release.id}/review`, { expected_revision: release.revision, operation: "approve_source", reason: "Reviewed synthetic fixture", source_reviewed: true })
  else
    expect(release.state).toBe("approved")
  const exports = path.join(directory, "exports")
  await mkdir(exports, { mode: 0o700 })
  await writeFile(path.join(directory, "config.json"), JSON.stringify({ output_root: exports }), { mode: 0o600 })
  const publicRequest = JSON.parse(python(["-c", "import sys,json; from pathlib import Path; from test_package_installation import sdk; from airalogy_instrument_gateway.package_contract import sha256; from airalogy_instrument_gateway.installation_manager import prepare; root=Path(sys.argv[1]); wheel=sdk(); (root/'sdk.whl').write_bytes(wheel); print(json.dumps(prepare(destination=root/'private.json', platform_url=sys.argv[2], lab_id=sys.argv[3], gateway_id=sys.argv[4], package=root/'synthetic.zip', sdk_wheel=root/'sdk.whl', trusted_sdk_digest=sha256(wheel), config=root/'config.json', root=root)))", directory, api, fixtures.lab.id, gateway.id]))
  await confirm("/instrument-installations", { request: publicRequest, resource_id: resource.id, release_id: release.id, reason: "Synthetic software test", fingerprint_confirmed: true })
  python(["-m", "airalogy_instrument_gateway.installation_manager_cli", "apply", path.join(directory, "private.json"), "--source-reviewed"])
  const now = Date.now()
  const qualification = await confirm(`/instrument-installations/${publicRequest.id}/qualifications`, {
    id: randomUUID(),
    scope: "read_only",
    evidence_origin: "manual_observation",
    target: Object.fromEntries(["identity_reference", "firmware", "application", "application_version", "driver_version", "os_version"].map(key => [key, "Synthetic policy fixture, no hardware"])),
    commands: [{ key: "reader.measure", version: "1.0.0", checks: ["identity", "output", "completion"].map(kind => ({ kind, method: "Synthetic policy check", expected: "42", observed: "42", passed: true })) }],
    evidence_file_ids: [],
    assessed_at: new Date(now).toISOString(),
    expires_at: new Date(now + 86400000).toISOString(),
    reason: "Synthetic policy fixture, not physical acceptance",
    independent_review_confirmed: true,
    physical_tests_authorized: true,
  })
  const active = await confirm(`/instrument-installations/${publicRequest.id}/activations`, { id: randomUUID(), qualification_id: qualification.id, expected_active_id: null, commands: ["reader.measure@1.0.0"], expires_at: new Date(now + 3600000).toISOString(), reason: "Synthetic policy fixture, no hardware", activation_confirmed: true })
  const task = await confirm("/research-tasks", { project_id: fixtures.project.id, title: `Synthetic file review ${suffix}`, goal: "Review exact synthetic file provenance", success_criteria: ["Traceable reviewed outcome"], tool_keys: ["knowledge.search"], resource_type_ids: [kind.id] })
  await call(`/research-tasks/${task.id}/start`, { expected_revision: task.revision, reason: "Synthetic test" })
  const booking = await call(`${base}/bookings`, { resource_id: resource.id, starts_at: new Date(now - 60000).toISOString(), ends_at: new Date(now + 3600000).toISOString(), purpose: "Synthetic file test", idempotency_key: randomUUID() })
  const action = await confirm(`/research-tasks/${task.id}/instrument-actions`, { command_id: active.commands[0].id, equipment_booking_id: booking.id, arguments: { sample_count: 2 }, idempotency_key: randomUUID() })
  const credentials = path.join(directory, "gateway.json")
  await writeFile(credentials, JSON.stringify({ schema: "airalogy.gateway-credential.v1", platform_url: api, lab_id: fixtures.lab.id, gateway_id: gateway.id, gateway_token: token }), { mode: 0o600 })
  const startupArgs = ["--request", path.join(directory, "private.json"), "--credentials", credentials, "--activation", active.id, "--output-root", exports]
  const startup = JSON.parse(python(["-m", "airalogy_instrument_gateway.activation_cli", "preview", ...startupArgs]))
  python(["-m", "airalogy_instrument_gateway.activation_cli", "run", ...startupArgs, "--startup-authorized", "--confirm-digest", startup.preview_digest, "--once"])
  const outputsUrl = `/research-instrument-jobs/${action.instrument_job.id}/outputs`
  const output = await call(outputsUrl, undefined, "GET")
  expect(output.state).toBe("delivered")
  expect(output.items[0].state).toBe("registered")
  return { fixtures, api, headers, call, confirm, task, outputsUrl, output }
}

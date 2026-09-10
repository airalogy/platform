import { Buffer } from "node:buffer"
import { randomUUID } from "node:crypto"
import { join } from "node:path"
import { canonical, digest } from "./contract.mjs"
import { Evidence } from "./evidence.mjs"
import { validateNativeDefinition, validateNativeSelection } from "./native-contract.mjs"
import { nativeCall, nativeFailureCode, validateNativeBuild } from "./native-transport.mjs"
import { validateSurveyReport } from "./survey-contract.mjs"

export async function selectNative({ buildFile, bundlePath, pid, title, locale = "en-US", captureValues = false, redactIdentifiers = [] }) {
  const pin = await nativeCall(buildFile, { operation: "pin_process", bundle_path: bundlePath, pid })
  return validateNativeSelection({
    schema: "airalogy.native-survey-selection.v1",
    id: "selected.native.application",
    build_file: buildFile,
    target: { application: pin.bundle.bundle_id, version: pin.bundle.version, title, locale, source: { kind: "native_macos", pin } },
    capture_values: captureValues,
    redact_identifiers: redactIdentifiers,
  })
}

export async function previewNativeSurvey(input, { verifyTarget = true } = {}) {
  const selection = validateNativeSelection(JSON.parse(canonical(input)))
  const { manifest } = await validateNativeBuild(selection.build_file)
  const selected = selection.target.source.pin
  if (verifyTarget) {
    const current = await nativeCall(selection.build_file, { operation: "pin_process", bundle_path: selected.bundle.bundle_path, pid: selected.process.pid })
    if (canonical(current) !== canonical(selected))
      throw new Error("Selected native application or process changed; review a new selection")
  }
  const engine = { name: "macos_accessibility_read_only", version: 1, build: manifest, os: (await nativeCall(selection.build_file, { operation: "doctor" })).os_version }
  const data = { schema: "airalogy.interface-survey-preview.v1", engine, definition: selection }
  return { ...data, sha256: digest(data) }
}

export async function captureNative(selection) {
  return nativeCall(selection.build_file, { operation: "snapshot", pin: selection.target.source.pin, window_title: selection.target.title, capture_values: selection.capture_values, redact_identifiers: selection.redact_identifiers }, { timeout: 30000 })
}

export async function runNativeSurvey(selection, { confirmation, evidenceRoot }) {
  const preview = await previewNativeSurvey(selection)
  if (confirmation !== preview.sha256)
    throw new Error("Confirm the exact native process, window and capture policy")
  const evidence = await Evidence.create(evidenceRoot, preview)
  await evidence.append("native_read_intent", { preview_digest: preview.sha256, actions_approved: false })
  try {
    const captured = await captureNative(preview.definition)
    const report = validateSurveyReport({
      schema: "airalogy.interface-survey.v1",
      id: randomUUID(),
      preview_digest: preview.sha256,
      target: { application: selection.target.application, version: selection.target.version, title: selection.target.title, locale: selection.target.locale, kind: "native_macos" },
      capture_values: selection.capture_values,
      controls: captured.controls,
      omitted_private: captured.omitted_private,
      limitations: ["Read-only macOS Accessibility snapshot of an explicitly selected existing process; no app launched or action executed.", "Bundle integrity and process lifetime are pinned, not vendor trust or hardware identity.", "Accessibility metadata and geometry are application-reported, not pixel visibility or physical safety evidence.", "Input values are opt-in; passwords and declared private regions are omitted. Review other labels/static text before model processing.", "Only unique AX identifiers are addressable; unsupported or ambiguous controls require manual mapping."],
    })
    await evidence.write("survey.json", Buffer.from(canonical(report)))
    await evidence.append("native_survey_captured", { report_digest: digest(report), actions_executed: 0, hardware_qualified: false })
    return { evidence: evidence.directory, report_file: join(evidence.directory, "survey.json"), report_digest: digest(report), actions_executed: 0, hardware_qualified: false }
  }
  catch (error) {
    await evidence.append("native_read_refused", { retry_allowed: false, reason: nativeFailureCode(error) })
    throw new Error(`Native survey refused; retain private evidence: ${evidence.directory}`)
  }
}

export async function previewNativeRead(input) {
  const definition = validateNativeDefinition(JSON.parse(canonical(input)))
  const survey = await previewNativeSurvey(definition.selection)
  const value = { schema: "airalogy.native-read-preview.v1", definition, engine: survey.engine }
  return { ...value, sha256: digest(value) }
}

export async function runNativeRead(definition, { confirmation, evidenceRoot }) {
  const preview = await previewNativeRead(definition)
  if (preview.sha256 !== confirmation)
    throw new Error("Confirm the exact reviewed native read definition")
  const evidence = await Evidence.create(evidenceRoot, preview)
  await evidence.append("native_read_intent", { preview_digest: preview.sha256, actions_approved: false })
  try {
    const captured = await captureNative(preview.definition.selection)
    const found = locator => captured.controls.filter(item => item.locator && canonical(item.locator) === canonical(locator))
    const identity = found(preview.definition.identity.locator)
    if (identity.length !== 1 || identity[0].read !== "text" || identity[0].value !== preview.definition.identity.text)
      throw new Error("Native identity anchor changed")
    const values = {}
    for (const control of preview.definition.controls) {
      const matched = found(control.locator)
      if (matched.length !== 1 || matched[0].read !== control.read)
        throw new Error("Reviewed native control changed or is no longer addressable")
      values[control.id] = matched[0].value
    }
    await evidence.write("readback.json", Buffer.from(canonical(values)))
    await evidence.append("native_read_completed", { readback_digest: digest(values), actions_executed: 0, hardware_qualified: false })
    return { readback_file: join(evidence.directory, "readback.json"), actions_executed: 0, hardware_qualified: false }
  }
  catch (error) {
    await evidence.append("native_read_refused", { retry_allowed: false, reason: nativeFailureCode(error) })
    throw new Error(`Native read refused; retain private evidence: ${evidence.directory}`)
  }
}

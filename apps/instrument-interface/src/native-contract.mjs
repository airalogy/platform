import { Buffer } from "node:buffer"
import { canonical, checkKey, checkObject, checkText } from "./contract.mjs"

export function validateNativeLocator(locator) {
  checkObject(locator, ["kind", "role", "name"])
  if (locator.kind !== "ax_identifier" || !["AXStaticText", "AXTextField", "AXTextArea", "AXButton", "AXCheckBox", "AXRadioButton", "AXPopUpButton", "AXComboBox", "AXSlider", "AXTabGroup"].includes(locator.role))
    throw new Error("Select a supported unique Accessibility identifier")
  checkText(locator.name)
  return locator
}

export function validateNativePin(pin) {
  checkObject(pin, ["bundle", "process"])
  validateNativeBundle(pin.bundle)
  checkObject(pin.process, ["pid", "uid", "started_seconds", "started_microseconds"])
  for (const name of ["pid", "uid"]) {
    if (!Number.isInteger(pin.process[name]) || pin.process[name] < (name === "pid" ? 1 : 0) || pin.process[name] > 2147483647)
      throw new Error("Select an exact native process")
  }
  for (const name of ["started_seconds", "started_microseconds"]) {
    if (typeof pin.process[name] !== "string" || !/^\d{1,20}$/.test(pin.process[name]))
      throw new Error("Pin the process lifetime")
  }
  return pin
}

export function validateNativeBundle(bundle) {
  checkObject(bundle, ["bundle_path", "bundle_id", "version", "executable_path", "executable_sha256", "code_directory_hash", "info_sha256"])
  for (const name of ["bundle_path", "executable_path"])
    checkText(bundle[name], 4096)
  for (const name of ["bundle_id", "version"])
    checkText(bundle[name])
  for (const name of ["executable_sha256", "info_sha256"]) {
    if (typeof bundle[name] !== "string" || !/^[a-f0-9]{64}$/.test(bundle[name]))
      throw new Error("Pin native bundle bytes")
  }
  if (typeof bundle.code_directory_hash !== "string" || !/^[a-f0-9]{40}$/.test(bundle.code_directory_hash))
    throw new Error("Pin native code identity")
  return bundle
}

export function validateNativeSelection(value) {
  if (Buffer.byteLength(canonical(value)) > 131072)
    throw new Error("Native selection exceeds its bound")
  checkObject(value, ["schema", "id", "target", "build_file", "capture_values", "redact_identifiers"])
  if (value.schema !== "airalogy.native-survey-selection.v1" || typeof value.capture_values !== "boolean")
    throw new Error("Native survey requires an explicit capture policy")
  checkKey(value.id)
  checkText(value.build_file, 4096)
  checkObject(value.target, ["application", "version", "title", "locale", "source"])
  for (const name of ["application", "version", "title", "locale"])
    checkText(value.target[name])
  checkObject(value.target.source, ["kind", "pin"])
  if (value.target.source.kind !== "native_macos")
    throw new Error("Select a supported native transport")
  const { pin } = value.target.source
  validateNativePin(pin)
  if (value.target.version !== pin.bundle.version)
    throw new Error("Native version and code identity must match the selected bundle")
  if (!Array.isArray(value.redact_identifiers) || value.redact_identifiers.length > 32 || new Set(value.redact_identifiers).size !== value.redact_identifiers.length)
    throw new Error("Select at most 32 distinct private-region identifiers")
  value.redact_identifiers.forEach(name => checkText(name))
  return value
}

export function validateNativeDefinition(definition) {
  checkObject(definition, ["schema", "id", "selection", "identity", "controls"])
  if (definition.schema !== "airalogy.native-read-definition.v1")
    throw new Error("Only read-only native definitions are currently supported")
  checkKey(definition.id)
  validateNativeSelection(definition.selection)
  checkObject(definition.identity, ["locator", "text"])
  validateNativeLocator(definition.identity.locator)
  checkText(definition.identity.text)
  if (definition.identity.locator.role !== "AXStaticText" || !Array.isArray(definition.controls) || !definition.controls.length || definition.controls.length > 17)
    throw new Error("Select a visible static identity and bounded native reads")
  const ids = new Set()
  const locators = new Set()
  for (const control of definition.controls) {
    checkObject(control, ["id", "locator", "read", "operations"])
    checkKey(control.id)
    validateNativeLocator(control.locator)
    const key = canonical(control.locator)
    if (ids.has(control.id) || locators.has(key) || canonical(control.operations) !== "[\"read\"]" || !["text", "value"].includes(control.read) || (control.read === "value" && !definition.selection.capture_values))
      throw new Error("Native definitions cannot add duplicate targets, actions or value consent")
    if (control.read === "text" ? control.locator.role !== "AXStaticText" : !["AXTextField", "AXTextArea"].includes(control.locator.role))
      throw new Error("Native read type must match the observed role")
    ids.add(control.id)
    locators.add(key)
  }
  return definition
}

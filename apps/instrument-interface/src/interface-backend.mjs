import { BrowserInterfaceSession, previewInterface } from "./browser-session.mjs"
import { NativeInterfaceSession, previewNativeInterface } from "./native-session.mjs"

// Trusted static dispatch only. A model cannot supply a module or executable.
function backend(definition) {
  if (definition?.schema === "airalogy.browser-interface.v1")
    return { preview: previewInterface, session: BrowserInterfaceSession }
  if (definition?.schema === "airalogy.native-interface.v1")
    return { preview: previewNativeInterface, session: NativeInterfaceSession }
  throw new Error("Select a reviewed supported action definition, not a read-only survey")
}

export function previewSelectedInterface(definition, plan, policy = null) {
  return backend(definition).preview(definition, plan, policy)
}

export function openSelectedInterface(options) {
  return backend(options.definition).session.open(options)
}

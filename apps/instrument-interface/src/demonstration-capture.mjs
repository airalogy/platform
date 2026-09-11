/* eslint-disable unicorn/prefer-dom-node-text-content -- Match the approved visible-text readback, never hidden DOM text. */

// Trusted browser-side instrumentation. Receives selected element handles only;
// no selectors, application code, raw keystrokes, screenshots or host operations.
// This is evidence from an owned page, not authentication of a human or hardware.
export function installDemonstrationCapture({ controls, binding, statusKey }) {
  const status = { active: true, busy: false, pending: false, ignored: 0 }
  Object.defineProperty(window, statusKey, { value: status })
  let edit = null
  let press = null
  let click = null
  const targetOf = event => controls.find(item => item.element === event.target || item.element.contains(event.target))
  const block = (event) => {
    event.preventDefault()
    event.stopImmediatePropagation()
  }
  const read = () => {
    const values = {}
    const enabled = {}
    for (const item of controls) {
      const element = item.element
      if (!element.isConnected)
        throw new Error("Selected control was replaced")
      values[item.id] = item.read === "value" ? element.value : item.read === "checked" ? element.checked : element.innerText
      enabled[item.id] = !element.matches(":disabled") && element.getAttribute("aria-disabled") !== "true"
    }
    return { values, enabled }
  }
  const stop = () => {
    if (!status.active)
      return
    status.active = false
    void window[binding]({ kind: "stopped" }).catch(() => {})
  }
  const submit = (operation, selected, before) => {
    if (!status.active || status.busy) {
      stop()
      return
    }
    let after
    try {
      after = read()
    }
    catch {
      stop()
      return
    }
    status.busy = true
    status.pending = false
    void window[binding]({ kind: "step", operation, control_id: selected.id, before, after }).then((accepted) => {
      status.busy = false
      if (accepted !== true)
        status.active = false
    }).catch(() => {
      status.active = false
      status.busy = false
    })
  }
  const guard = (event) => {
    if (!status.active || status.busy) {
      block(event)
      status.ignored += 1
      return false
    }
    if (!event.isTrusted) {
      block(event)
      stop()
      return false
    }
    return true
  }
  // Retain pre-default-action state for pointer and keyboard button activation.
  // No actual key values or pointer coordinates enter evidence.
  for (const type of ["pointerdown", "keydown"]) {
    document.addEventListener(type, (event) => {
      if (!guard(event))
        return
      const selected = targetOf(event)
      if (selected?.operations.includes("click") && (type === "pointerdown" || ["Enter", " "].includes(event.key))) {
        try {
          press = { selected, before: read() }
        }
        catch { stop() }
      }
    }, true)
  }
  document.addEventListener("beforeinput", (event) => {
    if (!guard(event))
      return
    const selected = targetOf(event)
    if (!selected?.operations.includes("fill") || (edit && edit.selected !== selected)) {
      block(event)
      stop()
      return
    }
    try {
      edit ??= { selected, before: read() }
      status.pending = true
    }
    catch {
      block(event)
      stop()
    }
  }, true)
  document.addEventListener("input", (event) => {
    if (!event.isTrusted || !edit || targetOf(event) !== edit.selected)
      stop()
  }, true)
  document.addEventListener("change", (event) => {
    if (!event.isTrusted || !edit || targetOf(event) !== edit.selected) {
      stop()
      return
    }
    const selected = edit
    edit = null
    submit("fill", selected.selected, selected.before)
  })
  document.addEventListener("click", (event) => {
    if (!guard(event))
      return
    const selected = targetOf(event)
    if (selected?.operations.includes("click")) {
      if (edit || press?.selected !== selected) {
        block(event)
        stop()
        return
      }
      click = press
      press = null
    }
    else if (!selected && event.target.closest("button,a,input,select,textarea,[role=button],[contenteditable=true]")) {
      block(event)
      stop()
    }
  }, true)
  document.addEventListener("click", (event) => {
    if (click && targetOf(event) === click.selected) {
      const selected = click
      click = null
      submit("click", selected.selected, selected.before)
    }
  })
}

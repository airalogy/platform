import { Buffer } from "node:buffer"
import { randomBytes } from "node:crypto"
import { BrowserInterfaceSession, previewInterface } from "./browser-session.mjs"
import { canonical, checkObject, digest } from "./contract.mjs"
import { installDemonstrationCapture } from "./demonstration-capture.mjs"
import { Evidence } from "./evidence.mjs"
import { matches } from "./exploration-contract.mjs"
import { validateState } from "./workflow.mjs"

const stateOf = ({ state, values, enabled }) => ({ state, values, enabled })
const same = (left, right) => canonical(left) === canonical(right)
const locate = (root, spec) => spec.kind === "role" ? root.getByRole(spec.role, { name: spec.name, exact: true }) : root.getByTestId(spec.name)

export async function previewDemonstration(definition, policy, { visible = true } = {}) {
  if (typeof visible !== "boolean" || definition?.target?.source?.kind !== "file" || definition?.network?.length !== 0)
    throw new Error("Demonstration supports explicitly reviewed offline owned HTML only")
  const { sha256: _, ...selected } = await previewInterface(definition, { schema: "airalogy.interface-plan.v1", steps: [] }, policy)
  if (!selected.policy?.actions.some(action => action.operation === "click" || action.operation === "fill"))
    throw new Error("Select an explicit demonstration action/success policy before opening a window")
  const preview = { ...selected, capture: { kind: "human_browser_events", visible } }
  return { ...preview, sha256: digest(preview) }
}

export class BrowserDemonstrationSession extends BrowserInterfaceSession {
  static async open({ definition, policy, confirmation, evidenceRoot, visible = true, acknowledgeOwnedSimulation = false }) {
    const preview = await previewDemonstration(definition, policy, { visible })
    if (acknowledgeOwnedSimulation !== true || confirmation !== preview.sha256)
      throw new Error("Confirm the exact target, action/capture policy and owned simulation before demonstration")
    const evidence = await Evidence.create(evidenceRoot, preview)
    const session = new BrowserDemonstrationSession(preview, evidence)
    session.headless = !visible
    try {
      await session.start()
      await session.installCapture()
      return session
    }
    catch {
      await session.fail("Demonstration setup failed; no automatic relaunch")
      throw new Error("Demonstration stopped; retain private evidence")
    }
  }

  async installCapture() {
    const snapshot = await this.snapshot()
    if (!same(snapshot.observation, this.lastObservation))
      throw new Error("Interface changed before recording was ready")
    const controls = []
    try {
      for (const control of this.definition.controls) {
        const locator = await this.unique(locate(snapshot.scope, control.locator))
        controls.push({ id: control.id, read: control.read, operations: control.operations, element: await locator.elementHandle() })
      }
      this.statusKey = `airalogy_record_${randomBytes(16).toString("hex")}`
      const binding = `airalogy_event_${randomBytes(16).toString("hex")}`
      await this.page.exposeBinding(binding, async (source, value) => {
        if (source.page !== this.page || source.frame !== this.page.mainFrame()) {
          await this.fail("Demonstration event came from another page/frame")
          return false
        }
        return this.record(value)
      })
      await this.page.evaluate(installDemonstrationCapture, { controls, binding, statusKey: this.statusKey })
    }
    finally {
      await Promise.all(controls.map(control => control.element?.dispose()))
    }
  }

  fromReadback(value) {
    checkObject(value, ["values", "enabled"])
    const states = this.definition.states.filter(state => matches(state.checks, value))
    if (states.length !== 1)
      throw new Error("Demonstrated state is unknown or ambiguous")
    return validateState({ ...value, state: states[0].id }, this.definition)
  }

  async record(value) {
    if (this.busy || this.closed || this.fault)
      return false
    this.busy = true
    try {
      this.remaining()
      if (Buffer.byteLength(canonical(value)) > 262144)
        throw new Error("Demonstration event exceeded its bound")
      checkObject(value, ["kind", "operation", "control_id", "before", "after"])
      if (value.kind !== "step" || !["click", "fill"].includes(value.operation) || this.cursor >= this.definition.limits.max_steps)
        throw new Error("Unexpected or excessive demonstration event")
      const before = this.fromReadback(value.before)
      const after = this.fromReadback(value.after)
      if (!same(before, stateOf(this.lastObservation)) || before.enabled[value.control_id] !== true)
        throw new Error("Unrecorded or concurrent interface change")
      const step = { operation: value.operation, control_id: value.control_id, before: before.state, after: after.state }
      if (step.operation === "fill")
        step.value = after.values[step.control_id]
      if (!this.policy.actions.some(action => same(action, step)))
        throw new Error("Demonstrated action is outside the reviewed literal policy")
      // The page's event report is untrusted. Independently recheck current
      // target, scope, privacy, unique controls and the exact post-action state.
      const current = await this.snapshot()
      if (!same(stateOf(current.observation), after))
        throw new Error("Demonstrated postcondition changed before recording")
      await this.evidence.append("demonstration_action", { index: this.cursor, step, before: digest(this.lastObservation) })
      const saved = await this.saveObservation(current)
      await this.evidence.append("demonstration_readback", { index: this.cursor, after: saved.sha256, value: saved.values[step.control_id] })
      this.cursor += 1
      return true
    }
    catch {
      await this.fail("Demonstration stopped; an observed or unrecorded action may have occurred. Do not replay automatically.")
      return false
    }
    finally { this.busy = false }
  }

  async finish() {
    if (this.busy || !this.cursor)
      throw new Error("Commit an input and wait for its recorded receipt before finishing")
    this.busy = true
    try {
      this.remaining()
      // Freeze further manual input before the final snapshot and durable
      // completion. Do not race a late browser event against finish/close.
      const status = await this.page.evaluate((key) => {
        const value = window[key]
        if (!value)
          return null
        const prior = { ...value }
        value.active = false
        return prior
      }, this.statusKey)
      if (!status?.active || status.busy || status.pending)
        throw new Error("An input or recording receipt is unfinished")
      const current = await this.snapshot()
      if (!same(stateOf(current.observation), stateOf(this.lastObservation)) || !matches(this.policy.success, current.observation))
        throw new Error("Final readback does not match the recorded steps and original success checks")
      await this.evidence.append("demonstration_result", { result: "observed_success", completed_steps: this.cursor, hardware_qualified: false })
      await this.close()
      return { evidence: this.evidence.directory, completed_steps: this.cursor, model_calls: 0, hardware_qualified: false }
    }
    catch {
      await this.fail("Demonstration incomplete; retain evidence without promotion or replay")
      throw new Error("Demonstration could not be completed")
    }
    finally { this.busy = false }
  }

  // This session records a person's browser events; it must never execute an
  // inherited fixed-plan/action-policy step itself.
  async step() { throw new Error("Demonstration records manual events, not agent actions") }
}

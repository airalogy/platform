import type { RecorderProposal, RecorderTurn } from "@airalogy/components/chat/providers/recorderTurn"
import { recorderTurnKey } from "@airalogy/components/chat/providers/recorderTurn"
import { cloneDeep, isEqual } from "lodash-es"
import { useDialog } from "naive-ui"
import { nanoid } from "nanoid"
import { onActivated, onDeactivated, onScopeDispose, provide, ref, shallowRef, watch } from "vue"
import { useI18n } from "vue-i18n"

interface RecorderOptions {
  scope: () => string
  version: () => string | undefined
  recordId: () => string | undefined
  editable: () => boolean
  fields: () => Record<string, { value?: unknown, assigner?: unknown }>
  write: (field: string, value: unknown) => Promise<void>
}

interface Edit {
  field: string
  before: unknown
  after: unknown
  revision?: number
}

function displayValue(value: unknown): unknown {
  return value && typeof value === "object" && "value" in value ? value.value : value
}
function empty(value: unknown) {
  const raw = displayValue(value)
  return raw == null || raw === ""
}
export function useRecorderConversation(options: RecorderOptions) {
  const { locale, t } = useI18n()
  const dialog = useDialog()
  const simulation = shallowRef<Record<string, unknown>>()
  const receipt = ref("")
  const edits = shallowRef<Edit[]>([])
  const lastApplied = ref<string[]>([])
  let formId = nanoid()
  const editRevisions = new Map<string, number>()
  let alive = true
  let activeRequest = ""
  let lastChatId: string | undefined
  function reset() {
    formId = nanoid()
    activeRequest = ""
    editRevisions.clear()
    edits.value = []
    receipt.value = ""
    simulation.value = undefined
    lastApplied.value = []
  }
  watch(options.scope, reset, { flush: "sync" })
  onActivated(() => {
    alive = true
  })
  onDeactivated(() => {
    alive = false
    reset()
  })
  onScopeDispose(() => {
    alive = false
  })

  function confirmOverwrite(changes: Edit[]) {
    return new Promise<boolean>((resolve) => {
      dialog.warning({
        title: t("page.recorderAira.replace"),
        content: changes.map(change => `${change.field}: ${String(displayValue(change.before))} → ${String(displayValue(change.after))}`).join("\n"),
        positiveText: t("common.confirm"),
        negativeText: t("common.cancel"),
        onPositiveClick: () => resolve(true),
        onNegativeClick: () => resolve(false),
        onClose: () => resolve(false),
        onAfterLeave: () => resolve(false),
      })
    })
  }

  function begin(chatId?: string): RecorderTurn | undefined {
    if (!alive || !options.editable() || !options.version() || simulation.value)
      return undefined
    const revisions = new Map(editRevisions)
    const touched = (field: string) => revisions.get(field) !== editRevisions.get(field)
    const before = new Map(Object.entries(options.fields()).map(([key, field]) => [key, cloneDeep(field.value)]))
    const target = {
      form_id: formId,
      request_id: nanoid(),
      version: options.version()!,
      record_id: options.recordId(),
      locale: locale.value === "zh-CN" ? "zh-CN" as const : "en-US" as const,
      filled: [...before].filter(([, value]) => !empty(value)).map(([key]) => key),
      last_applied: chatId && chatId === lastChatId ? [...lastApplied.value] : [],
    }
    activeRequest = target.request_id
    let consumed = false
    const current = () => alive && options.editable() && target.form_id === formId && activeRequest === target.request_id
    async function apply(proposal: RecorderProposal, serverChatId?: string) {
      if (consumed || !current() || proposal.request_id !== target.request_id || proposal.form_id !== target.form_id)
        return ""
      consumed = true
      if (proposal.intent !== "fill" && proposal.intent !== "simulate")
        return ""
      const skipped = new Set(proposal.skipped)
      const preserved = new Set<string>()
      const candidates: Edit[] = []
      for (const [field, after] of Object.entries(proposal.values)) {
        const node = options.fields()[field]
        if (touched(field) || !before.has(field) || !node || node.assigner || !isEqual(before.get(field), node.value))
          preserved.add(field)
        else
          candidates.push({ field, before: before.get(field), after })
      }
      const changed: Edit[] = []
      if (proposal.intent === "simulate") {
        const examples = candidates.filter(change => empty(change.before))
        simulation.value = Object.fromEntries(examples.map(change => [change.field, change.after]))
        changed.push(...examples)
      }
      else {
        const overwrites = candidates.filter(change => !empty(change.before) && !isEqual(change.before, change.after))
        const approved = !overwrites.length || await confirmOverwrite(overwrites)
        for (const change of candidates) {
          if (!current())
            return ""
          if (touched(change.field) || (!approved && overwrites.includes(change)) || !isEqual(options.fields()[change.field]?.value, change.before)) {
            preserved.add(change.field)
            continue
          }
          await options.write(change.field, change.after)
          changed.push({ ...change, after: cloneDeep(options.fields()[change.field].value), revision: editRevisions.get(change.field) })
        }
        if (changed.length) {
          lastChatId = serverChatId
          edits.value = changed
          lastApplied.value = changed.map(change => change.field)
        }
      }
      const label = t(proposal.intent === "simulate" ? "page.recorderAira.simulated" : "page.recorderAira.filled")
      receipt.value = [
        `${label} (${changed.length}): ${changed.map(x => x.field).join(", ")}`,
        skipped.size ? `${t("page.recorderAira.skipped")}: ${[...skipped].join(", ")}` : "",
        preserved.size ? `${t("page.recorderAira.preserved")}: ${[...preserved].join(", ")}` : "",
      ].filter(Boolean).join("\n")
      return receipt.value
    }
    return { target, apply }
  }
  provide(recorderTurnKey, { begin, enabled: () => Boolean(options.version()) && options.editable() && !simulation.value })
  async function undo() {
    const journal = edits.value
    edits.value = []
    const reverted = []
    for (const edit of journal) {
      if (alive && options.editable() && edit.revision === editRevisions.get(edit.field) && isEqual(options.fields()[edit.field]?.value, edit.after)) {
        await options.write(edit.field, edit.before)
        reverted.push(edit.field)
      }
    }
    lastApplied.value = []
    receipt.value = `${t("page.recorderAira.undone")}: ${reverted.join(", ")}`
  }
  function markInput(event: Event) {
    if (!(event.target instanceof Element))
      return
    const owner = event.target.closest<HTMLElement>("[data-recorder-field], [data-rec-focus-key]")
    const field = owner?.dataset.recorderField || owner?.dataset.recFocusKey?.replace(/^var:/, "")
    if (field)
      editRevisions.set(field, (editRevisions.get(field) || 0) + 1)
  }
  function exitSimulation() {
    simulation.value = undefined
    receipt.value = ""
  }
  return { begin, receipt, edits, undo, simulation, exitSimulation, markInput }
}

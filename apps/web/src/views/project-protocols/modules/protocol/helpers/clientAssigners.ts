import type { AimdRecordValidationSchema } from "@airalogy/aimd-recorder"
import type { Assigner } from "@airalogy/shared/types/models/protocol"
import { createAimdRecorderMessages, createEmptyProtocolRecordData, getAimdVarTableCellFieldKey, useClientAssignerRunner, validateAimdRecord } from "@airalogy/aimd-recorder"
import { parseAndExtract } from "@airalogy/aimd-renderer"
import { shallowRef } from "vue"

export function resolveProtocolAssigners(content: string, stored: Record<string, Assigner> = {}) {
  const result = { ...stored }
  const clients = parseAndExtract(content).client_assigner
  for (const client of clients) {
    for (const field of client.assigned_fields) {
      const previous = result[field]
      if (previous && previous.runtime !== "client")
        throw new Error(`Both client and server assigners write ${field}`)
      if (previous && (previous.id !== client.id || previous.mode !== client.mode || JSON.stringify(previous.dependent_fields) !== JSON.stringify(client.dependent_fields) || JSON.stringify(previous.assigned_fields) !== JSON.stringify(client.assigned_fields)))
        throw new Error(`Client assigner metadata does not match the Protocol: ${field}`)
      result[field] = client
    }
  }
  return result
}

/** Execute one node using the published runtime. The host owns scheduling/permissions. */
export function runProtocolClientAssigner(
  content: string,
  assigner: Assigner,
  dependencies: Record<string, unknown>,
  schema: AimdRecordValidationSchema | undefined,
  readonly = false,
  locale = "en-US",
) {
  if (readonly)
    throw new Error("Cannot calculate in a read-only Record")
  const fields = parseAndExtract(content)
  const definition = fields.client_assigner.find(item => item.id === assigner.id)
  if (!definition || assigner.runtime !== "client")
    throw new Error("Client assigner is not declared in this Protocol")
  const values = Object.fromEntries(definition.dependent_fields.map((field) => {
    const value = dependencies[field]
    if (value === undefined || value === null)
      throw new Error(`Missing dependency: ${field}`)
    return [field, value]
  }))
  const record = createEmptyProtocolRecordData()
  record.var = structuredClone(values)
  function validate(keys: string[], data: Record<string, unknown>) {
    if (!keys.length)
      return
    const candidate = createEmptyProtocolRecordData()
    const fieldKeys = keys.map((field) => {
      if (field.includes(".")) {
        const [table, column] = field.split(".")
        const rows = (candidate.var[table] ||= [{}]) as Record<string, unknown>[]
        rows[0][column] = data[field]
        return getAimdVarTableCellFieldKey(table, 0, column)
      }
      candidate.var[field] = data[field]
      return `var:${field}`
    })
    const result = validateAimdRecord(fields, candidate, {
      schema,
      fieldKeys,
      messages: createAimdRecorderMessages(locale).validation,
    })
    if (!result.valid)
      throw new Error(result.issues.map(issue => issue.message).join("; "))
  }
  validate(definition.dependent_fields, values)
  let error: string | undefined
  const runner = useClientAssignerRunner({
    readonly: () => readonly,
    clientAssigners: shallowRef([definition]),
    localRecord: record,
    onError: (message) => { error = message },
    emitRecordUpdate() {},
    scheduleInlineRebuild() {},
  })
  runner.runClientAssigners({ triggerIds: [definition.id] })
  if (error)
    throw new Error(error)
  const output = Object.fromEntries(definition.assigned_fields.map(field => [field, record.var[field]]))
  // Non-finite values must not turn into JSON null during persistence.
  JSON.stringify(output, (_key, value) => {
    if (value === undefined || (typeof value === "number" && !Number.isFinite(value)))
      throw new Error("Client assigner returned an invalid numeric or missing result")
    return value
  })
  validate(definition.assigned_fields, output)
  return output
}

import type { AnalysisField, AnalysisScalar } from "@/service/api/analysis"
import type { AnalysisSelection } from "./analysis-selection"

export function createAnalysisContextRequest(protocolId: string, selection?: AnalysisSelection) {
  const url = `/protocols/${protocolId}/analysis-context`
  if (selection === undefined)
    return { url, method: "GET" as const }
  if (!selection || !["latest", "selected"].includes(selection.mode))
    throw new Error("Analysis context requires an explicit valid selection")
  // A request must retain the selected revisions and filters even if the
  // reactive editor changes while the request is waiting in the network stack.
  return { url, method: "POST" as const, data: JSON.parse(JSON.stringify(selection)) as AnalysisSelection }
}

export function analysisFieldType(field?: AnalysisField): string {
  if (!field || field.unsupported_reason)
    return "unsupported"
  const raw = field.type
  if (Array.isArray(raw)) {
    const types = raw.filter(value => value !== "null")
    return types.length === 1 ? types[0] : "unsupported"
  }
  return raw || "unsupported"
}

export function parseAnalysisFieldOperand(value: string, field?: AnalysisField): AnalysisScalar {
  const type = analysisFieldType(field)
  if (type === "number" || type === "integer") {
    const parsed = Number(value)
    if (!value.trim() || !Number.isFinite(parsed) || (type === "integer" && !Number.isInteger(parsed)))
      throw new Error("invalid_numeric_value")
    return parsed
  }
  if (type === "boolean") {
    if (!["true", "false"].includes(value))
      throw new Error("invalid_boolean_value")
    return value === "true"
  }
  if (type !== "string")
    throw new Error("unsupported_field")
  return value
}

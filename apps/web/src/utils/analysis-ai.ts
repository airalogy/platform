import type { AnalysisAIRequest, AnalysisComputeMetric, AnalysisGroundedMetric, AnalysisResult, AnalysisSelection } from "@/service/api/analysis"

export function createAnalysisAIRequestId() {
  // randomUUID is unavailable on HTTP-only private Lab deployments.
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0F) | 0x40
  bytes[8] = (bytes[8] & 0x3F) | 0x80
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("")
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

/** A definite API rejection ends an attempt; an uncertain outcome keeps its id. */
export function shouldRecoverAnalysisAIRequest(error: unknown) {
  const status = (error as { response?: { status?: number } } | null)?.response?.status
  return !(typeof status === "number" && [400, 401, 403, 404, 409, 422, 429].includes(status))
}

export function analysisSelectionIdentity(selection: AnalysisSelection | null) {
  if (!selection)
    return ""
  if (selection.mode === "selected")
    return JSON.stringify(["selected", selection.records.map(record => [record.id, record.version]).sort((a, b) => String(a[0]).localeCompare(String(b[0])))])
  return JSON.stringify(["latest", Object.entries(selection.filters).filter(([, value]) => value !== undefined).sort(([a], [b]) => a.localeCompare(b))])
}

export function canAdoptAnalysisDraft(request: AnalysisAIRequest, protocolId: string, projectId: string, selection: AnalysisSelection | null) {
  return Boolean(selection && request.kind === "draft" && request.state === "generated"
    && request.protocol_id === protocolId && request.project_id === projectId
    && request.output && "mode" in request.output && request.output.mode === "builtin" && request.output.recipe
    && analysisSelectionIdentity(request.source_selection) === analysisSelectionIdentity(selection))
}

export function canAdoptAnalysisComputeDraft(request: AnalysisAIRequest, protocolId: string, projectId: string, selection: AnalysisSelection | null, environmentRevisionId: string | undefined, language: string | undefined) {
  const output = request.output
  return Boolean(selection && environmentRevisionId && language && request.kind === "compute_draft" && request.state === "generated"
    && request.protocol_id === protocolId && request.project_id === projectId
    && output && "mode" in output && output.mode === "compute" && output.recipe
    && output.recipe.environment_revision_id === environmentRevisionId && output.recipe.language === language
    && analysisSelectionIdentity(request.source_selection) === analysisSelectionIdentity(selection))
}

/** Strict RFC6901 scalar lookup against the sealed result, never a model value. */
export function resolveAnalysisComputeMetric(metric: AnalysisComputeMetric, computedResult: Record<string, unknown>): AnalysisComputeMetric | null {
  if (typeof metric.pointer !== "string" || !metric.pointer.startsWith("/") || /~(?:[^01]|$)/.test(metric.pointer))
    return null
  let current: unknown = computedResult
  for (const token of metric.pointer.slice(1).split("/")) {
    const key = token.replaceAll("~1", "/").replaceAll("~0", "~")
    if (current === null || typeof current !== "object" || !Object.hasOwn(current, key))
      return null
    if (Array.isArray(current) && !/^(?:0|[1-9]\d*)$/.test(key))
      return null
    current = (current as Record<string, unknown>)[key]
  }
  if (current !== null && !["string", "number", "boolean"].includes(typeof current))
    return null
  // JSON.parse cannot independently verify integers beyond JavaScript's exact
  // range: both the report and model value may already have rounded identically.
  if (typeof current === "number" && (!Number.isFinite(current) || (Number.isInteger(current) && !Number.isSafeInteger(current))))
    return null
  if (current !== metric.value)
    return null
  return { pointer: metric.pointer, value: current as AnalysisComputeMetric["value"] }
}

/** Return the stored statistic, never a model-provided replacement value. */
export function resolveAnalysisMetric(metric: AnalysisGroundedMetric, result: AnalysisResult): AnalysisGroundedMetric | null {
  const group = result.groups[metric.group_index]
  const field = result.fields.find(item => item.key === metric.field)
  const stats = group?.fields[metric.field]
  if (!group || !field || !stats || !Object.hasOwn(stats, metric.statistic))
    return null
  const unit = ["count", "missing", "invalid"].includes(metric.statistic) ? "" : field.unit || ""
  const groupIdentity = (key: typeof group.key) => JSON.stringify(key.map(item => [item.field, item.type, item.value]))
  if (metric.value !== stats[metric.statistic] || metric.n !== stats.count || metric.row_count !== group.row_count
    || (metric.unit || "") !== unit || groupIdentity(metric.group) !== groupIdentity(group.key)) {
    return null
  }
  return { ...metric, value: stats[metric.statistic], n: stats.count, row_count: group.row_count, group: group.key, unit }
}

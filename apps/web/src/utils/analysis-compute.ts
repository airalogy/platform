import type { AnalysisRecipe, AnalysisRun, BuiltinAnalysisRun } from "@/service/api/analysis"
import type { AnalysisComputeContext, AnalysisComputeEnvironment, AnalysisComputeInputFile, AnalysisComputeRecipe } from "@/service/api/analysis-compute"
import type { ProjectAnalysisRecipe } from "@/service/api/project-analysis"

export function isComputeAnalysisRecipe(recipe: AnalysisRecipe | AnalysisComputeRecipe | ProjectAnalysisRecipe): recipe is AnalysisComputeRecipe {
  return "kind" in recipe && recipe.kind === "compute"
}

export function isBuiltinAnalysisRun(run: AnalysisRun): run is BuiltinAnalysisRun {
  return !isComputeAnalysisRecipe(run.recipe)
}

export function parseAnalysisComputeParameters(text: string): Record<string, unknown> {
  const value: unknown = JSON.parse(text)
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("invalidParameters")
  const finite = (item: unknown): boolean => typeof item === "number" ? Number.isFinite(item) : item !== null && typeof item === "object" ? Object.values(item).every(finite) : true
  if (!finite(value))
    throw new Error("invalidParameters")
  return value as Record<string, unknown>
}

export function analysisComputeRecipeIdentity(recipe: AnalysisComputeRecipe) {
  const canonical = (value: unknown): unknown => Array.isArray(value) ? value.map(canonical) : value !== null && typeof value === "object" ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, canonical(item)])) : value
  return JSON.stringify(canonical(withAnalysisComputeInputFiles(recipe, recipe.input_files ?? [])))
}

/** Empty declarations keep existing saved-method JSON byte-compatible. */
export function withAnalysisComputeInputFiles(recipe: AnalysisComputeRecipe, inputFiles: AnalysisComputeInputFile[]): AnalysisComputeRecipe {
  const { input_files: _previousInputs, ...base } = recipe
  return inputFiles.length ? { ...base, input_files: inputFiles.map(input => ({ input_id: input.input_id, field_path: [...input.field_path] })) } : base
}

export function analysisComputeInputFileFieldLabel(field: { field_path: ["var", string], title: string, file_extensions: string[] | null }): string {
  return `${field.title || field.field_path[1]} [${field.field_path[1]}] (${field.file_extensions?.join(", ") || "*"})`
}

export function validateAnalysisComputeInputFiles(inputs: AnalysisComputeInputFile[], context: AnalysisComputeContext): string | null {
  if (!inputs.length)
    return null
  if (!context.input_file_fields || !context.input_file_limits)
    return "inputFilesUnavailable"
  if (inputs.length > 16)
    return "invalidInputFiles"
  const ids = new Set<string>()
  const paths = new Set<string>()
  for (const input of inputs) {
    const path = JSON.stringify(input.field_path)
    if (!/^[a-z][a-z0-9_]{0,23}$/.test(input.input_id) || ids.has(input.input_id) || paths.has(path)
      || !context.input_file_fields.some(field => JSON.stringify(field.field_path) === path)) {
      return "invalidInputFiles"
    }
    ids.add(input.input_id)
    paths.add(path)
  }
  return inputs.length * context.source.record_count > context.input_file_limits.max_files ? "tooManyInputFiles" : null
}

export function analysisComputeGovernance(maxCost: string, currency: string, deadline: number | null, now = Date.now()): { max_cost?: string, budget_currency?: string, deadline_at?: string } {
  const result: { max_cost?: string, budget_currency?: string, deadline_at?: string } = {}
  if (maxCost.trim()) {
    if (!/^\d+(?:\.\d{1,18})?$/.test(maxCost.trim()) || maxCost.replace(".", "").trim().length > 38)
      throw new Error("invalidCost")
    if (!/^[A-Z]{3}$/.test(currency.trim()))
      throw new Error("invalidCurrency")
    result.max_cost = maxCost.trim()
    result.budget_currency = currency.trim()
  }
  if (deadline !== null) {
    if (!Number.isFinite(deadline) || deadline <= now || deadline > 8.64e15)
      throw new Error("invalidDeadline")
    result.deadline_at = new Date(deadline).toISOString()
  }
  return result
}

export function validateAnalysisComputeRecipe(recipe: AnalysisComputeRecipe, context: AnalysisComputeContext): string | null {
  const environment = context.environments.find(item => item.revision_id === recipe.environment_revision_id)
  if (!environment)
    return "environmentUnavailable"
  if (!environment.authorized_runner_count)
    return "noAuthorizedRunner"
  if (!environment.allowed_languages.includes(recipe.language))
    return "invalidLanguage"
  if (!recipe.source_code.trim() || new TextEncoder().encode(recipe.source_code).byteLength > context.max_source_bytes)
    return "invalidSource"
  if (!recipe.parameters || typeof recipe.parameters !== "object" || Array.isArray(recipe.parameters))
    return "invalidParameters"
  const inputError = validateAnalysisComputeInputFiles(recipe.input_files ?? [], context)
  if (inputError)
    return inputError
  if (recipe.output_files.length > 16)
    return "invalidOutputs"
  const names = new Set<string>()
  let outputBytes = 0
  for (const output of recipe.output_files) {
    if (!/^[a-z0-9][\w.-]{0,127}$/i.test(output.mount_name) || names.has(output.mount_name)
      || !output.asset_name.trim() || !/^[a-z\d][\w!#$&^.+-]*\/[a-z\d][\w!#$&^.+-]*$/i.test(output.media_type)
      || !Number.isSafeInteger(output.max_bytes) || output.max_bytes < 1) {
      return "invalidOutputs"
    }
    names.add(output.mount_name)
    outputBytes += output.max_bytes
  }
  return outputBytes > Math.max(0, environment.resource_limits.max_output_bytes - 1024) ? "invalidOutputs" : null
}

export function analysisComputeEnvironmentLabel(environment: AnalysisComputeEnvironment) {
  return `${environment.name} · r${environment.revision}`
}

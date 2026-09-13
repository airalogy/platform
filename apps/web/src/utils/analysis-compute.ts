import type { AnalysisRecipe, AnalysisRun, BuiltinAnalysisRun } from "@/service/api/analysis"
import type { AnalysisComputeContext, AnalysisComputeEnvironment, AnalysisComputeRecipe } from "@/service/api/analysis-compute"

export function isComputeAnalysisRecipe(recipe: AnalysisRecipe | AnalysisComputeRecipe): recipe is AnalysisComputeRecipe {
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
  return JSON.stringify(canonical(recipe))
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

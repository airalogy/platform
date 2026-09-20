import type { AnalysisField, AnalysisRecipe, AnalysisRecordReference } from "@/service/api/analysis"
import type { ProjectAnalysisRecipe, ProjectAnalysisSelection, ProjectAnalysisSlot } from "@/service/api/project-analysis"

/** A late method response must never replace a newer method or explicit rerun. */
export function createProjectEditorLoader(onLoading: (loading: boolean) => void) {
  let sequence = 0
  return {
    cancel() {
      sequence += 1
      onLoading(false)
    },
    async load<T>(request: () => Promise<T>, apply: (value: T) => void): Promise<boolean> {
      const current = ++sequence
      onLoading(true)
      try {
        const value = await request()
        if (current !== sequence)
          return false
        apply(value)
        return true
      }
      catch (error) {
        if (current === sequence)
          throw error
        return false
      }
      finally {
        if (current === sequence)
          onLoading(false)
      }
    },
  }
}

export function isProjectAnalysis(value: unknown): value is { recipe: ProjectAnalysisRecipe } {
  return Boolean(value && typeof value === "object" && "recipe" in value && value.recipe && typeof value.recipe === "object" && "kind" in value.recipe && value.recipe.kind === "project")
}
export function emptyProjectStatistics(): AnalysisRecipe {
  return { schema_version: 1, numeric_fields: [], group_by: [], filters: [], missing_policy: "exclude", chart: "none" }
}
/** A reactive array can contain nested proxies even after toRaw(array). */
export function copyProjectRecordReferences(records: readonly AnalysisRecordReference[]): AnalysisRecordReference[] {
  return records.map(record => ({ id: record.id, version: record.version }))
}
export function newProjectAnalysisSlot(existing: ProjectAnalysisSlot[], label: string): ProjectAnalysisSlot {
  let index = 1
  while (existing.some(slot => slot.slot_id === `input_${index}`))
    index += 1
  return { slot_id: `input_${index}`, label, recipe: emptyProjectStatistics() }
}
/** Explicit reruns change only selections, never the saved scope or recipe. */
export function projectAnalysisLatest(selection: ProjectAnalysisSelection): ProjectAnalysisSelection {
  return { schema: "airalogy.project-selection.v1", inputs: selection.inputs.map(input => ({ slot_id: input.slot_id, protocol_id: input.protocol_id, selection: { mode: "latest", filters: {} } })) }
}
export function projectAnalysisIdentity(value: ProjectAnalysisRecipe | ProjectAnalysisSelection): string {
  const canonical = (item: unknown): unknown => Array.isArray(item) ? item.map(canonical) : item !== null && typeof item === "object" ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b)).map(([key, child]) => [key, canonical(child)])) : item
  return JSON.stringify(canonical(value))
}
export function projectFieldType(field?: AnalysisField): string {
  if (!field || field.unsupported_reason)
    return "unsupported"
  const types = Array.isArray(field.type) ? field.type.filter(type => type !== "null") : [field.type]
  return types.length === 1 ? types[0] : "unsupported"
}
export function projectJoinFieldsCompatible(left?: AnalysisField, right?: AnalysisField): boolean {
  const type = projectFieldType(left)
  return ["string", "number", "integer", "boolean"].includes(type) && type === projectFieldType(right) && (left?.unit || null) === (right?.unit || null)
}
export function projectAnalysisValidation(recipe: ProjectAnalysisRecipe, selection: ProjectAnalysisSelection, fields: Record<string, AnalysisField[]>): string | null {
  if (recipe.slots.length < 2 || recipe.slots.length > 8 || (recipe.mode === "relational" && recipe.slots.length !== 2))
    return "invalidSlots"
  const ids = recipe.slots.map(slot => slot.slot_id)
  if (new Set(ids).size !== ids.length || selection.inputs.length !== ids.length
    || new Set(selection.inputs.map(input => input.protocol_id)).size !== ids.length
    || selection.inputs.some(input => !ids.includes(input.slot_id) || (input.selection.mode === "selected" && !input.selection.records.length))) {
    return "invalidSlots"
  }
  for (const slot of recipe.slots) {
    if (!slot.label.trim() || !selection.inputs.find(input => input.slot_id === slot.slot_id)?.protocol_id || !slot.recipe.numeric_fields.length)
      return "incompleteSlot"
    const sourceFields = fields[slot.slot_id] || []
    if (slot.recipe.numeric_fields.some(key => !sourceFields.some(field => field.key === key && ["number", "integer"].includes(projectFieldType(field)))))
      return "invalidFields"
    if ([...slot.recipe.group_by, ...slot.recipe.filters.map(filter => filter.field)].some(key => !sourceFields.some(field => field.key === key && ["string", "number", "integer", "boolean"].includes(projectFieldType(field)))))
      return "invalidFields"
  }
  if (recipe.mode !== "relational")
    return recipe.join === null ? null : "invalidJoin"
  const join = recipe.join
  if (!join || !ids.includes(join.left_slot_id) || !ids.includes(join.right_slot_id) || join.left_slot_id === join.right_slot_id || !join.keys.length)
    return "invalidJoin"
  if (join.keys.some(key => !projectJoinFieldsCompatible(fields[join.left_slot_id]?.find(field => field.key === key.left_field), fields[join.right_slot_id]?.find(field => field.key === key.right_field))))
    return "incompatibleKeys"
  if (!join.outputs.length || !join.recipe.numeric_fields.length || new Set(join.outputs.map(output => output.output_id)).size !== join.outputs.length)
    return "invalidOutputs"
  for (const output of join.outputs) {
    const field = fields[output.slot_id]?.find(field => field.key === output.field)
    if (!/^[a-z][a-z0-9_]{0,23}$/.test(output.output_id) || !output.semantic_label.trim() || !field || !["string", "number", "integer", "boolean"].includes(projectFieldType(field)) || (field.unit || null) !== output.unit)
      return "invalidOutputs"
  }
  if (join.recipe.numeric_fields.some(key => !join.outputs.some(output => output.output_id === key && ["number", "integer"].includes(projectFieldType(fields[output.slot_id]?.find(field => field.key === output.field)))))
    || [...join.recipe.group_by, ...join.recipe.filters.map(filter => filter.field)].some(key => !join.outputs.some(output => output.output_id === key))) {
    return "invalidOutputs"
  }
  return join.semantic_alignment_confirmed ? null : "confirmSemantics"
}

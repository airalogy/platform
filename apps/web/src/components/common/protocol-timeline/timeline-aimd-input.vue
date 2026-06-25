<template>
  <aimd-input v-bind="aimdInputProps" />
</template>

<script setup lang="ts">
import { isObject } from "lodash-es"

interface Props {
  data: any
  cellKey?: string
}

const props = withDefaults(defineProps<Props>(), {
  cellKey: "data",
})

// Create a proper IFieldItem model
const fieldModel = reactive({
  label: "",
  value: props.data,
  disabled: true, // Read-only for timeline display
  required: false,
  scope: "display" as any,
  title: "",
  type: getAIMDType(props.data),
  id: `timeline-cell-${props.cellKey}`,
})

// Update value when props change
watch(() => props.data, (newData) => {
  fieldModel.value = newData
  fieldModel.type = getAIMDType(newData)
}, { deep: true })

// AIMD input props with sensible defaults
const aimdInputProps = computed(() => {
  return {
    type: getAIMDType(props.data),
    prop: props.cellKey,
    model: fieldModel,
    id: `timeline-cell-${props.cellKey}`,
    scope: "display" as any,
    info: {},
    themeOverrides: {},
    disabled: true, // Read-only for timeline display
    placeholder: "",
    enumInfo: {},
    assigner: undefined,
    dependent: [],
    ajvInfo: undefined,
  }
})

// Get aimd type based on data value - aligned with timeline-data-cell.vue type system
function getAIMDType(value: any): string {
  // For aimd input, we use the internal type system for component selection
  if (typeof value === "boolean")
    return "boolean"
  if (typeof value === "number")
    return "number"
  if (typeof value === "string")
    return "text"
  if (isObject(value)) {
    // File objects - aligned with timeline-data-cell asset detection
    if ("filename" in value && "id" in value)
      return "file"
    if ("airalogy_file_id" in value)
      return "file"
    if ("file_extension" in value)
      return "file"

    // Check/annotation objects - aligned with timeline-data-cell
    if ("annotation" in value || "checked" in value)
      return "rs-check"

    // Support for additional aimd types
    if ("mode" in value && "dependent_fields" in value)
      return "assigner"
    if ("scope" in value && "value" in value)
      return "variable"
  }
  return "text"
}
</script>

<style scoped>
.timeline-cell-display {
  width: 100%;
}
</style>

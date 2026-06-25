<template>
  <span v-if="targetName" :class="refClassName">
    <!-- Step reference -->
    <n-tooltip v-if="isStepRef && stepSequence" trigger="hover">
      <template #trigger>
        <n-text :depth="1" class="step-ref-text">
          {{ $t("common.stepIndex", { index: stepSequence }) }}
        </n-text>
      </template>
      <template #default>
        <div class="step-ref-tooltip">
          <div class="step-ref-tooltip__header">
            <span class="step-ref-tooltip__sequence">{{ $t("common.stepIndex", { index: stepSequence }) }}</span>
          </div>
          <div class="step-ref-tooltip__content">
            <n-ellipsis :line-clamp="3">
              {{ stepContent || $t("common.noContent") }}
            </n-ellipsis>
          </div>
        </div>
      </template>
    </n-tooltip>
    <!-- Variable reference -->
    <n-tooltip v-else-if="isVarRef" trigger="hover">
      <template #trigger>
        <n-text :depth="1" class="var-ref-text">
          {{ displayVarValue }}
        </n-text>
      </template>
      <template #default>
        <div class="var-ref-tooltip">
          <div class="var-ref-tooltip__header">
            <span class="var-ref-tooltip__name">{{ targetName }}</span>
          </div>
          <div v-if="varTitle" class="var-ref-tooltip__title">
            {{ varTitle }}
          </div>
          <div v-if="varValue !== null && varValue !== undefined && varValue !== ''" class="var-ref-tooltip__value">
            {{ $t("common.value") }}: {{ displayVarValue }}
          </div>
          <div v-else class="var-ref-tooltip__empty">
            {{ $t("common.noValue") }}
          </div>
        </div>
      </template>
    </n-tooltip>
    <!-- Reference not found (only for step references that don't exist) -->
    <n-text v-else-if="isStepRef" type="error">{{ $t("common.referenceNotFound") }}</n-text>
  </span>
</template>

<script setup lang="ts">
import { useAIMDInject } from "../composables/useAIMDHelpers"

/**
 * Props for AimdStepRef component
 * Simplified from IAIMDItemProps - only uses what's needed
 */
interface AimdStepRefProps {
  /** Reference target name */
  name: string
  /** Reference type: 'step' or 'var' */
  type: "step" | "var"
  /** Optional: direct refStep value (legacy) */
  refStep?: string
  /** Optional: info object containing env.record.byName */
  info?: {
    env?: {
      record?: {
        byName?: Record<string, { step?: string, content?: string }>
      }
    }
  }
  /** Optional: variable item props (for var references) */
  varItem?: any
  /** Optional: context value (for var references) */
  contextValue?: Record<string, Record<string, unknown>>
}

const props = defineProps<AimdStepRefProps>()

// Get AIMD context for variable references (may be undefined in some contexts)
const aimdContext = useAIMDInject()

// Use refStep if provided (legacy), otherwise use name
const targetName = computed(() => props.refStep || props.name)

// Determine reference type
const isStepRef = computed(() => props.type === "step")
const isVarRef = computed(() => props.type === "var")

// Class name based on reference type
const refClassName = computed(() => {
  if (isStepRef.value) {
    return "research-step-ref"
  }
  else if (isVarRef.value) {
    return "research-var-ref"
  }
  return "research-ref"
})

// Step reference data
const stepSequence = computed(() => {
  if (!targetName.value || !isStepRef.value)
    return null

  // Get the step reference from the environment
  const stepRecord = props.info?.env?.record?.byName?.[targetName.value]
  return stepRecord?.step || null
})

const stepContent = computed(() => {
  if (!targetName.value || !isStepRef.value)
    return null

  // Try to get content from the original step
  const stepRecord = props.info?.env?.record?.byName?.[targetName.value]
  return stepRecord?.content || null
})

// Variable reference data
const varScopeRecord = computed(() => aimdContext?.varScopeRecord?.value || {})
const fieldModel = computed(() => aimdContext?.fieldModel || {})

const varScope = computed(() => {
  if (!targetName.value || !isVarRef.value)
    return null
  return varScopeRecord.value[targetName.value] || "research_variable"
})

const varValue = computed(() => {
  if (!targetName.value || !isVarRef.value)
    return undefined

  // Try to get value from props.contextValue first (passed from renderer)
  if (props.contextValue) {
    // Try research_variable scope first
    let fieldData = props.contextValue.research_variable?.[targetName.value]

    // If not found, try to find in other scopes
    if (!fieldData && props.contextValue) {
      for (const scope of Object.keys(props.contextValue)) {
        if (props.contextValue[scope]?.[targetName.value]) {
          fieldData = props.contextValue[scope][targetName.value]
          break
        }
      }
    }

    if (fieldData) {
      // Extract value from field data structure
      if (typeof fieldData === "object" && fieldData !== null && "value" in fieldData) {
        return (fieldData as { value: unknown }).value
      }
      return fieldData
    }
  }

  // Fallback to injected context
  if (!varScope.value)
    return undefined

  const fieldData = fieldModel.value[varScope.value]?.[targetName.value]
  if (!fieldData)
    return undefined

  // Extract value from field data structure
  if (typeof fieldData === "object" && fieldData !== null && "value" in fieldData) {
    return (fieldData as { value: unknown }).value
  }

  return fieldData
})

const displayVarValue = computed(() => {
  if (varValue.value === undefined || varValue.value === null || varValue.value === "") {
    return targetName.value
  }
  return String(varValue.value)
})

const varTitle = computed(() => {
  if (!targetName.value || !isVarRef.value)
    return null

  // Try to get title from varItem first (passed from renderer)
  if (props.varItem && "title" in props.varItem) {
    return props.varItem.title as string
  }

  // Fallback to injected context
  if (!varScope.value)
    return null

  const fieldData = fieldModel.value[varScope.value]?.[targetName.value]
  if (fieldData && typeof fieldData === "object" && "title" in fieldData) {
    return fieldData.title as string
  }

  return null
})
</script>

<style scoped lang="sass">
.research-step-ref,
.research-var-ref
  cursor: pointer
  color: var(--primary-color)
  font-weight: 500

.step-ref-text,
.var-ref-text
  border-bottom: 1px dashed currentColor
  padding-bottom: 1px

.step-ref-tooltip,
.var-ref-tooltip
  max-width: 300px

  &__header
    margin-bottom: 8px
    font-weight: 600

  &__sequence,
  &__name
    display: inline-block
    color: var(--primary-color)

  &__content,
  &__value
    font-size: 0.9em
    color: var(--text-color-2)

  &__title
    margin-bottom: 4px
    font-size: 0.85em
    color: var(--text-color-3)

  &__empty
    font-size: 0.9em
    color: var(--text-color-3)
    font-style: italic
</style>

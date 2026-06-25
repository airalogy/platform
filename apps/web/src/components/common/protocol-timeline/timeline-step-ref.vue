<template>
  <span v-if="refStep" class="research-step-ref">
    <n-tooltip v-if="stepSequence" trigger="hover">
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
    <n-text v-else type="error">{{ $t("common.referenceNotFound") }}</n-text>
  </span>
</template>

<script setup lang="ts">
import type { IAIMDItemProps } from "../../custom/aimd/types/aimd-types"

const props = defineProps<IAIMDItemProps & { refStep?: string }>()

const stepSequence = computed(() => {
  if (!props.refStep)
    return null

  // Get the step reference from the environment
  const stepRecord = props.info?.env?.record?.byName?.[props.refStep]
  return stepRecord?.step || null
})

const stepContent = computed(() => {
  if (!props.refStep)
    return null

  // Try to get content from the original step
  const stepRecord = props.info?.env?.record?.byName?.[props.refStep]
  return stepRecord?.content || null
})
</script>

<style scoped lang="sass">
.research-step-ref
  cursor: pointer
  color: var(--primary-color)
  font-weight: 500

.step-ref-text
  border-bottom: 1px dashed currentColor
  padding-bottom: 1px

.step-ref-tooltip
  max-width: 300px

  &__header
    margin-bottom: 8px
    font-weight: 600

  &__sequence
    display: inline-block
    color: var(--primary-color)

  &__content
    font-size: 0.9em
    color: var(--text-color-2)
</style>

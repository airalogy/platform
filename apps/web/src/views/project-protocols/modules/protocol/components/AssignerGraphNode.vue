<template>
  <div
    class="assigner-node nopan"
    :class="[
      `assigner-node--${nodeType}`,
      { 'assigner-node--selected': selected },
      { 'assigner-node--highlighted': isHighlighted },
      { 'assigner-node--dimmed': isDimmed },
    ]"
    @click="handleClick"
  >
    <handle
      v-if="hasTargetHandle"
      type="target"
      :position="Position.Left"
      :connectable="false"
    />
    <div class="assigner-node__content">
      <div class="assigner-node__label">
        {{ displayLabel }}
      </div>
    </div>
    <handle
      v-if="hasSourceHandle"
      type="source"
      :position="Position.Right"
      :connectable="false"
    />
  </div>
</template>

<script setup lang="ts">
import type { NodeProps } from "@vue-flow/core"
import { Handle, Position } from "@vue-flow/core"

interface NodeData {
  name: string
  title?: string
  type: "assigned_field" | "dependent_field" | "assigner"
  schemaInfo?: {
    title?: string
    type?: string
    format?: string
    description?: string
  }
  showTitle?: boolean
  isHighlighted?: boolean
  isDimmed?: boolean
}

interface IProps extends NodeProps<NodeData> {}

const props = defineProps<IProps>()
const emit = defineEmits<{
  (e: "nodeClick", nodeId: string, nodeType: string, event: MouseEvent): void
}>()

const nodeType = computed(() => props.data.type)
const selected = computed(() => props.selected)
const isHighlighted = computed(() => props.data.isHighlighted ?? false)
const isDimmed = computed(() => props.data.isDimmed ?? false)

const displayLabel = computed(() => {
  if (props.data.showTitle && props.data.schemaInfo?.title) {
    return props.data.schemaInfo.title
  }
  return props.data.name
})

// All nodes have both handles for better edge routing
const hasTargetHandle = computed(() => true)
const hasSourceHandle = computed(() => true)

function handleClick(event: MouseEvent) {
  event.stopPropagation()
  emit("nodeClick", props.id, nodeType.value, event)
}
</script>

<style scoped lang="sass">
.assigner-node
  @apply px-4 py-2 rounded-lg border-2 cursor-pointer transition-all duration-200
  @apply flex items-center justify-center
  min-width: 120px
  max-width: 200px

  &--dependent_field
    @apply bg-blue-50 border-blue-400 text-blue-700

  &--assigned_field
    @apply bg-green-50 border-green-500 text-green-700

  &--assigner
    @apply bg-pink-50 border-pink-500 text-pink-700 rounded-full
    min-width: 100px

  &--selected
    @apply ring-2 ring-offset-2 ring-blue-500 shadow-lg

  &--highlighted
    @apply ring-2 ring-offset-2 ring-yellow-400 shadow-lg

  &--dimmed
    @apply opacity-30

  &:hover:not(&--dimmed)
    @apply shadow-md

  &__content
    @apply flex items-center gap-2

  &__label
    @apply text-sm font-medium truncate
    max-width: 160px

:deep(.vue-flow__handle)
  @apply w-2 h-2 border-none opacity-0 pointer-events-none
  background: transparent !important
</style>

<template>
  <n-popconfirm
    v-for="action in visibleActions"
    :key="action.id"
    :trigger="action.confirmMessage ? 'click' : 'manual'"
    @positive-click="action.handler(item)"
    @update:show="(val: boolean) => handleUpdateShowState(val, action.id)"
  >
    <template #trigger>
      <n-button
        quaternary
        class="action-button"
        :class="{ 'action-button--active': activeActionId === action.id }"
        @click.stop="handleClick($event, action)"
      >
        <template #icon>
          <n-icon size="12">
            <component :is="action.icon" />
          </n-icon>
        </template>
      </n-button>
    </template>
    <template v-if="action.confirmMessage" #default>
      {{ action.confirmMessage(item) }}
    </template>
  </n-popconfirm>
</template>

<script setup lang="ts">
import type { Component } from "vue"
import type { TreeViewElement } from "./index.vue"

export interface Action {
  id: string
  icon: Component
  handler: (item: TreeViewElement) => void
  confirmMessage?: (item: TreeViewElement) => string
  condition?: (item: TreeViewElement) => boolean
}

interface Props {
  item: TreeViewElement
  actions: Action[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: "action", actionId: string, item: TreeViewElement): void
}>()

const activeActionId = ref<string | null>(null)

const visibleActions = computed(() => {
  return props.actions.filter((action) => {
    return !action.condition || action.condition(props.item)
  })
})

function handleUpdateShowState(isShown: boolean, actionId: string) {
  activeActionId.value = isShown ? actionId : null
}

function handleClick(e: PointerEvent | MouseEvent, action: Action) {
  if (action.confirmMessage) {
    return
  }

  action.handler(props.item)
  emit("action", action.id, props.item)
}
</script>

<style scoped lang="sass">
.action-button
  @apply mx-0.5 h-5 w-5 opacity-0 group-hover:opacity-70 hover:opacity-100
  &--active
    @apply opacity-100!
</style>

<template>
  <div class="relative h-full overflow-hidden">
    <div
      class="group min-h-[22px] w-full flex items-center justify-between border-[1px] border-[#202327] text-sm" :class="[
        {
          'bg-muted rounded-md': isSelect && isSelectable,
          'cursor-pointer': isSelectable,
          'cursor-not-allowed opacity-50': !isSelectable,
          'bg-[#3f86f5]/30 border-[#3f86f5]': selectedId === value,
        },
      ]"
      @click="onFolderClick"
    >
      <div class="flex items-center justify-start gap-x-1">
        <n-icon>
          <component :is="isExpanded ? openIcon : closeIcon" />
        </n-icon>
        <span>{{ element }}</span>
      </div>
    </div>
    <div v-if="!empty && isExpanded" class="relative h-full overflow-hidden text-sm">
      <tree-indicator v-if="indicator" />
      <div class="overflow-ellipsis ml-3 flex flex-col gap-1 overflow-hidden whitespace-nowrap py-1 rtl:mr-5">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { NIcon } from "naive-ui"
import { storeToRefs } from "pinia"
import { computed } from "vue"
import { useWebContainerStore } from "../../../store/webContainerStore"
import { useTreeContext } from "../composables/useTreeContext"
import TreeIndicator from "./TreeIndicator.vue"

interface Props {
  element: string
  value: string
  isSelectable?: boolean
  isSelect?: boolean
  empty?: boolean
  path: string
}

const props = withDefaults(defineProps<Props>(), {
  isSelectable: true,
  empty: false,
})

const { direction, selectedId, selectItem, expendedItems, handleExpand, indicator, openIcon, closeIcon } = useTreeContext()
const isExpanded = computed(() => expendedItems.value?.includes(props.value))

const { webContainerInstance } = storeToRefs(useWebContainerStore())

function onFolderClick() {
  handleExpand(props.value)
  selectItem(props.value)
}
</script>

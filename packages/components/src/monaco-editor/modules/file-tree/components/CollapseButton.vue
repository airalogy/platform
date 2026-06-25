<template>
  <n-button
    quaternary
    class="absolute bottom-1 right-2 h-8 w-fit p-1"
    @click="handleClick"
  >
    <slot />
    <span class="sr-only">Toggle</span>
  </n-button>
</template>

<script setup lang="ts">
import type { TreeViewElement } from "../types"
import { NButton } from "naive-ui"
import { watch } from "vue"
import { isDirectory } from "../../../utils"
import { useTreeContext } from "../composables/useTreeContext"

interface Props {
  elements: TreeViewElement[]
  expandAll?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  expandAll: false,
})

function handleClick() {
  if (props.expandAll) {
    expendAllTree(props.elements)
  }
  else {
    closeAll()
  }
}
const { expendedItems, setExpendedItems } = useTreeContext()

function expendAllTree(elements: TreeViewElement[]) {
  const expandTree = (element: TreeViewElement) => {
    const isSelectable = isDirectory(element) && (element.isSelectable ?? true)
    if (isSelectable && element.children && element.children.length > 0) {
      setExpendedItems?.([...(expendedItems.value ?? []), element.id])
      element.children.forEach(expandTree)
    }
  }
  elements.forEach(expandTree)
}

function closeAll() {
  setExpendedItems?.([])
}

watch(() => props.expandAll, (newValue) => {
  if (newValue) {
    expendAllTree(props.elements)
  }
})
</script>

import type { Ref } from "vue"
import type { TreeContextState, TreeProps, TreeViewElement } from "../types"
import { inject, provide, ref, watch } from "vue"
import { isDirectory } from "../../../utils"

export const treeContextKey = Symbol("treeContext")

export function useProvideTreeContext(props: TreeProps) {
  const selectedId = ref<string | undefined>(props.initialSelectedId)
  const expendedItems = ref<string[] | undefined>(props.initialExpendedItems)

  function selectItem(id: string) {
    selectedId.value = id
  }

  function handleExpand(id: string) {
    expendedItems.value = expendedItems.value?.includes(id)
      ? expendedItems.value.filter(item => item !== id)
      : [...(expendedItems.value ?? []), id]
  }

  function expandSpecificTargetedElements(elements?: TreeViewElement[], selectId?: string) {
    if (!elements || !selectId)
      return

    const findParent = (currentElement: TreeViewElement, currentPath: string[] = []) => {
      const isSelectable = isDirectory(currentElement) && (currentElement.isSelectable ?? true)
      const newPath = [...currentPath, currentElement.id]

      if (currentElement.id === selectId) {
        if (isSelectable) {
          expendedItems.value = [...(expendedItems.value ?? []), ...newPath]
        }
        else {
          if (newPath.includes(currentElement.id)) {
            newPath.pop()
            expendedItems.value = [...(expendedItems.value ?? []), ...newPath]
          }
        }
        return
      }

      if (isSelectable && currentElement.children && currentElement.children.length > 0) {
        currentElement.children.forEach((child) => {
          findParent(child, newPath)
        })
      }
    }

    elements.forEach((element) => {
      findParent(element)
    })
  }

  watch(() => props.initialSelectedId, (newId) => {
    if (newId) {
      expandSpecificTargetedElements(props.elements as any, newId)
    }
  })

  const context: TreeContextState = {
    selectedId: selectedId as Ref<string | undefined>,
    expendedItems: expendedItems as Ref<string[] | undefined>,
    indicator: props.indicator ?? true,
    handleExpand,
    selectItem,
    setExpendedItems: items => expendedItems.value = items,
    openIcon: props.openIcon,
    closeIcon: props.closeIcon,
    direction: props.dir ?? "ltr",
  }

  provide<TreeContextState>(treeContextKey, context)

  return context
}

export function useTreeContext() {
  const context = inject<TreeContextState>(treeContextKey)
  if (!context)
    throw new Error("useTreeContext must be used within a TreeProvider")
  return context
}

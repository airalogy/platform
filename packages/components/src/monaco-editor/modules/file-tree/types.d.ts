import type { Component, Ref } from "vue"

export type TreeViewElement = FileSystemItem

export interface TreeContextState {
  selectedId: Ref<string | undefined>
  expendedItems: Ref<string[] | undefined>
  indicator: boolean
  handleExpand: (id: string) => void
  selectItem: (id: string) => void
  setExpendedItems?: (items: string[] | undefined) => void
  openIcon?: Component
  closeIcon?: Component
  direction: "rtl" | "ltr"
}

export interface TreeProps {
  initialSelectedId?: string
  indicator?: boolean
  elements?: TreeViewElement[] | null
  initialExpendedItems?: string[]
  openIcon?: Component
  closeIcon?: Component
  dir?: "rtl" | "ltr"
}

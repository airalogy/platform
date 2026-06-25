export type ComboBoxItemType =
  | "contextProvider"
  | "slashCommand"
  | "file"
  | "query"
  | "folder"
  | "action"

export interface ComboBoxSubAction {
  label: string
  icon: string
  action: (item: ComboBoxItem) => void
}

export interface ComboBoxItem {
  title: string
  description: string
  id?: string
  content?: string
  type: ComboBoxItemType
  query?: string
  label?: string
  icon?: string
  action?: () => void
  contextProvider?: {
    type: string
    id: string
  }
  subActions?: ComboBoxSubAction[]
}

export type ContextProviderType = "normal" | "query" | "submenu"

export interface ContextProviderDescription {
  title: string
  displayTitle: string
  description: string
  renderInlineAs?: string
  type: ContextProviderType
}

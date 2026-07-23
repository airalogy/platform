import type { Protocol } from "@/types"
import type { IFieldItem } from "@/views/project-protocols/modules/protocol/types/types"

export interface IAIMDInputProps {
  type: string
  prop: string
  assigner?: Protocol.Assigner
  model: IFieldItem
  id: string
  disabled?: boolean
  required?: boolean
  scope: Protocol.ScopeFieldKey
  info: Record<string, any>
  placeholder?: string
  themeOverrides: any
  dependent?: { name: string, scope: IRecordDataKey }[]
  enumInfo?: Record<string, any>
  ajvInfo?: any
  isReference?: boolean // Flag to indicate this is a reference field (used for ref_var)
}

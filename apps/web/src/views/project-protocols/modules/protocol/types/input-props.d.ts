import type { Protocol } from "@/types/protocol"
import type { IFieldItem } from "./types"

export interface BaseInputProps {
  model: IFieldItem
  scope: IRecordDataKey
  prop: string
  inputId: string
  readonly?: boolean
  assigner?: Protocol.Assigner
  dependent?: { name: string, scope: IRecordDataKey }[]
  placeholder?: string
  type?: string
}

export interface InputPropsOptions extends BaseInputProps {
  ajvInfo?: any
  info?: Record<string, any>
  themeOverrides?: any
  enumInfo?: any
  id?: string
}

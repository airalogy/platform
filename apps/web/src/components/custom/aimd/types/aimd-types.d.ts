import type { ExtractResult } from "@/views/project-protocols/modules/protocol/helpers/parseFieldStructure"
import type { IRecordDataKey, ScopeFieldKey } from "@airalogy/aimd-core/types"
import type { Assigner } from "@airalogy/shared/types/models/protocol"
import type { FieldItem } from "@airalogy/shared/types/models/protocol"
import type { ValidateFunction } from "ajv"

export type { ICustomInputNumberPayload } from "./custom-input-number/index"

export type JsonSchema = Record<"title" | "type" | "description" | "format" | "airalogy_built_in_type" | "airalogy_type" | "build_in_rv_type" | "input_type" | "file_extension", string>

export interface IAIMDWrapperProps {
  protocolId: string
  record: ExtractResult | null
  propList: (string | [string, string[]])[][]
  scopeList: ScopeFieldKey[]
  typed?: Record<string, Record<string, Record<string, string>>>
  refRecord: Record<"ref_step" | "rv_ref", Record<string, any>>
  tableRecord: Record<
    string,
    Record<
      string,
      JsonSchema &
      {
        sequence: number
        assigner?: Assigner
        dependent?: { name: string, scope: IRecordDataKey }[]
        enum?: string[]
        anyOf?: JsonSchema[]
      }
    >
  >
  varScopeRecord: Record<string, ScopeFieldKey>
  readonly?: boolean
  assignerLoadingRecord: Record<string, boolean | undefined>
  assignerErrorRecord: Record<string, string | boolean | undefined>
  assignerRequestRecord: Record<string, { requestId: string, prop: string }>
}

export interface IAIMDItemProps {
  // to: string
  type: string
  id: string
  scope: ScopeFieldKey
  fieldType: string
  prop: string
  model: any
  placeholder?: string
  tooltip?: string
  info: Record<string, any>
  disabled?: boolean
  required?: boolean
  themeOverrides?: any
  assigner?: Protocol.Assigner
  dependent?: { name: string, scope: IRecordDataKey }[]
  dependentRecord?: Record<string, { name: string, scope: IRecordDataKey }[]>
  title?: string
  ajvInfo?: ValidateFunction | null
  enumInfo?: Record<string, any>
  isReference?: boolean // Flag to indicate this is a reference field (used for ref_var)
}

export type FieldRecord = {
  [k in string]: FieldItem
}

export type IFieldModel = {
  [GroupName in Protocol.ScopeFieldKey]: {
    [PropName in string]: {
      value:
        | string
        | number
        | boolean
        | { checked: boolean | null, annotation: string }
        | ICustomInputNumberPayload
        | undefined
        | Record<string, undefined | string | ICustomInputNumberPayload>[]
    }
  }
}

export interface IEmits {
  (e: "update:value", val: string): void
  (e: "add-row:table", payload: any): void
  (e: "remove-row:table", payload: any): void
  (e: "click:field", event: MouseEvent): void
}

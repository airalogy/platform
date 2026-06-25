import type { ICustomInputNumberPayload } from "@/components/custom/custom-input-number/types"
import type { ProtocolModels } from "@airalogy/shared/types"

export interface IFieldItem {
  label: string
  value?: any
  disabled: boolean
  required: boolean
  scope: Protocol.ScopeFieldKey
  title: string
  description?: string
  type: string
  pattern?: string
  group?: string
  children?: IFieldItem[]
  raw?: FieldItem
  assigner?: ProtocolModels.Assigner
  assignerRecord?: Record<string, ProtocolModels.Assigner>
  assignedSet?: Set<string>
  dependent?: { name: string, scope: IRecordDataKey }[]
  dependentRecord?: Record<string, { name: string, scope: IRecordDataKey }[]>
  name?: string
  originalName?: string
  link?: Record<"source" | "target", { name: string, prop: string }> & { isSource?: boolean }
  airalogy_file_id?: string
  info?: Record<string, any>
  id: string
  links?: {
    source: { name: string, prop: string }
    target: { name: string, prop: string }
    isSource: boolean
    type?: "one-to-one" | "one-to-many"
  }
  onUpdate?: (value: any) => void
}

export interface IFieldChangePayload {
  scope: IRecordDataKey
  prop: string
  type?: string
  value:
    | string
    | Partial<ICustomInputNumberPayload>
    | { formattedValue: string, value: string | number | undefined }
    | { filename: string, airalogy_file_id: string, type: string }
    | number
    | boolean
    | undefined
    | Array
    | null
  shouldUpdate?: boolean
  shouldAssign?: boolean
  attachmentInfo?: Api.Attachment.AttachmentItem
  fileInfo?: UploadFileInfo
  info?: Record<string, any>
  assigner?: ProtocolModels.Assigner
  dependent?: { name: string, scope: IRecordDataKey }[]
}

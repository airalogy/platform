import type { IAnnotationDataItem, IFileDataItem } from "@airalogy/shared"
import type { ICustomInputNumberPayload } from "../../components/custom/custom-input-number/types"

export interface ITimelineItem {
  id: string
  /** @deprecated: Fetch protocol info from record */
  isProtocolMatch?: boolean
  time: string
  operator: string
  operatorId: string
  operatorUsername: string
  order: number | string
  field: IRecordData
  protocolId?: string
  recordId?: string
  record?: RecordInfo
  recordVersion?: number
  protocolVersion?: string
}

export type IRecordDataItem =
  | string
  | number
  | boolean
  | IAnnotationDataItem
  | IFileDataItem
  | ICustomInputNumberPayload

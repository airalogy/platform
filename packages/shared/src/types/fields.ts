/**
 * Field types for protocol/AIMD system
 * Common types re-exported from @airalogy/aimd-core.
 * App-specific types (with ajv/naive-ui dependencies) remain here.
 */

import type { ValidateFunction } from "ajv"
import type { FormItemRule } from "naive-ui"

// Re-export common types from aimd-core
export type {
  FieldKey,
  FieldResponseKey,
  FiledName,
  IRecordDataKey,
  ScopeFieldKey,
} from "@airalogy/aimd-core/types"

import type { IRecordDataKey } from "@airalogy/aimd-core/types"

export type IRecordData = Record<
  IRecordDataKey,
  Record<
    string,
    IRecordDataItem | IRecordDataItem[]
  >
>

export interface IAnnotationDataItem {
  annotation: string
  checked: boolean | null
}

export interface IFileDataItem {
  id: string
  filename: string
  url: string
  type: "image" | "file"
  airalogy_file_id?: string
  content_type?: string | null
  size_bytes?: number | null
  sha256?: string | null
  storage_backend?: string | null
  storage_namespace?: string | null
}

export type FieldRecord = {
  [k in string]: IFieldItem
}

export interface ExtractResult {
  field: Partial<Record<import("@airalogy/aimd-core/types").ScopeFieldKey, FieldRecord>>
  rules: Partial<Record<import("@airalogy/aimd-core/types").FieldKey, Partial<Record<string, { ajv: ValidateFunction | null, value: FormItemRule }>>>>
}

export interface IFieldItem {
  name: string
  title?: string
  description?: string
  type?: string
  default?: any
  required?: boolean
  line_number?: number
  scope?: string
  [key: string]: any
}

export interface IRecordDataItem {
  name: string
  value?: any
  annotation?: string
  checked?: boolean | null
  files?: IFileDataItem[]
  [key: string]: any
}

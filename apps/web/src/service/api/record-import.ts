import { request } from "../request"

export interface RecordImportField {
  id: string
  title: string
  required: boolean
  schema: Record<string, any>
}
export interface RecordImportIssue {
  code?: string
  column?: string | null
  row_number?: number | null
  line_number?: number | null
  message?: string
}
export interface RecordImportTemplate {
  protocol_name: string
  protocol_version: string
  fields: RecordImportField[]
  csv: string
}
export interface RecordImportPreview extends Omit<RecordImportTemplate, "csv"> {
  row_count: number | null
  valid_count: number
  errors: RecordImportIssue[]
  preview_token: string | null
}

export async function fetchRecordImportTemplate(protocolId: string) {
  const { data, error } = await request<RecordImportTemplate>({
    url: `/protocols/${protocolId}/records/import-template`,
    metadata: { showError: false },
  })
  if (error)
    throw error
  if (!data)
    throw new Error("No template returned")
  return data
}

export async function previewRecordImport(protocolId: string, file: File, inputFormat: string) {
  const body = new FormData()
  body.append("file", file)
  body.append("input_format", inputFormat)
  body.append("preview", "true")
  const { data, error } = await request<RecordImportPreview>({
    url: `/protocols/${protocolId}/records/import`,
    method: "POST",
    data: body,
    timeout: 5 * 60 * 1000,
    metadata: { showError: false },
  })
  if (error)
    throw error
  if (!data)
    throw new Error("No preview returned")
  return data
}

export function groupImportIssues(issues: RecordImportIssue[]) {
  const grouped = new Map<string, { issue: RecordImportIssue, count: number, locations: number[], physicalLines: boolean }>()
  for (const issue of issues) {
    const key = JSON.stringify([issue.column, issue.code, issue.message, Boolean(issue.line_number)])
    let group = grouped.get(key)
    if (!group) {
      group = { issue, count: 0, locations: [], physicalLines: Boolean(issue.line_number) }
      grouped.set(key, group)
    }
    group.count++
    const location = issue.line_number ?? issue.row_number
    if (location && !group.locations.includes(location))
      group.locations.push(location)
  }
  return [...grouped.values()]
}

export function canConfirmRecordImport(preview: RecordImportPreview | null) {
  return Boolean(preview?.preview_token && preview.valid_count > 0 && preview.errors.length === 0)
}

export function importFieldType(schema: Record<string, any>): string {
  if (Array.isArray(schema.anyOf))
    return schema.anyOf.map(importFieldType).join(" / ")
  return schema.type || schema.airalogy_type || schema.$ref?.split("/").at(-1) || "JSON"
}

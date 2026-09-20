import type { IFieldChangePayload } from "@/views/project-protocols/modules/protocol/types/types"
import type { InjectionKey } from "vue"

/** A field item without this parent keeps its standalone file-event bridge. */
export const protocolFileEventOwnerKey: InjectionKey<boolean> = Symbol("protocol-file-event-owner")

type FileEventPayload = Omit<IFieldChangePayload, "value"> & { value?: unknown }

function objectValue(value: unknown): Record<string, any> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, any> : undefined
}

function fileReference(current: unknown): string | undefined {
  const item = Array.isArray(current) ? current[0] : current
  const reference = typeof item === "string" ? item : objectValue(item)?.airalogy_file_id
  return typeof reference === "string" && reference.startsWith("airalogy.id.file.") ? reference : undefined
}

export function isCurrentFileUpload(current: unknown, uploadId: unknown): boolean {
  return typeof uploadId === "string" && Array.isArray(current)
    && current.some(file => objectValue(file)?.id === uploadId
      && file.status !== "removed" && !fileReference(file))
}

function renamedFileValue(current: unknown, renamed: Record<string, any>): unknown {
  const item = Array.isArray(current) ? current[0] : current
  const metadata = objectValue(item)
  const reference = typeof item === "string" ? item : metadata?.airalogy_file_id
  if (typeof reference !== "string" || !reference.startsWith("airalogy.id.file."))
    return undefined

  // Rename responses may contain only the UUID, filename and URL. Never replace
  // the persisted FileId with that partial metadata (or another file's result).
  if (typeof renamed.id !== "string"
    || ![metadata?.id, reference, reference.split(".")[3]].includes(renamed.id)
    || (renamed.airalogy_file_id !== undefined && renamed.airalogy_file_id !== reference)) {
    return undefined
  }

  const updated: Record<string, any> = { ...metadata, airalogy_file_id: reference }
  if (typeof renamed.filename === "string") {
    updated.filename = renamed.filename
    updated.name = renamed.filename
  }
  if (typeof renamed.url === "string") {
    updated.url = renamed.url
    updated.thumbnailUrl = renamed.url
  }
  return Array.isArray(current) ? [updated, ...current.slice(1)] : updated
}

/** Convert preview-only events to the existing canonical field update contract. */
export function previewFileFieldChange(event: string, payload: FileEventPayload, currentValue?: unknown): IFieldChangePayload | undefined {
  const { scope, prop, info, assigner, dependent } = payload
  const value = objectValue(payload.value)
  if (!value)
    return undefined

  let updated: unknown
  let shouldAssign = false
  if (event === "preview-file-change") {
    if (value.type === "remove") {
      updated = null
      shouldAssign = true
    }
    else if (value.type === "add" && Array.isArray(value.file?.fileList)) {
      updated = value.file.fileList.map((file: unknown) => ({ ...objectValue(file) }))
    }
    else {
      return undefined
    }
  }
  else if (event === "preview-file-uploaded") {
    // A completed request must still belong to the selected local upload.
    // Deletion, replacement and repeated completion callbacks cannot revive it.
    const uploadId = payload.fileInfo?.id
    if (!isCurrentFileUpload(currentValue, uploadId))
      return undefined
    if (!fileReference(value))
      return undefined
    updated = { ...value }
    shouldAssign = true
  }
  else if (event === "preview-file-metadata") {
    // Loading an existing attachment is presentation hydration, not an upload.
    const reference = fileReference(currentValue)
    if (!reference || reference !== fileReference(value))
      return undefined
    updated = { ...value }
  }
  else if (event === "preview-file-renamed") {
    updated = renamedFileValue(currentValue, value)
    if (updated === undefined)
      return undefined
  }
  else {
    return undefined
  }

  return { scope, prop, value: updated as IFieldChangePayload["value"], info: info ? { ...info } : undefined, assigner, dependent, shouldUpdate: true, shouldAssign }
}

/** Return an existing literal field location; never create paths or unwrap cell values. */
export function previewFileTarget(
  fieldModel: Record<string, any>,
  payload: Pick<FileEventPayload, "scope" | "prop" | "info">,
): { owner: Record<string, any>, key: string } | undefined {
  const { scope, prop, info } = payload
  if (scope === "var_table") {
    if (!info || typeof info.group !== "string" || !Number.isInteger(info.row) || info.row < 0)
      return undefined
    const row = fieldModel.research_variable?.[info.group]?.value?.[info.row]
    if (!objectValue(row) || !Object.hasOwn(row, prop))
      return undefined
    return { owner: row, key: prop }
  }
  const fields = fieldModel[scope]
  if (!fields || !Object.hasOwn(fields, prop) || !objectValue(fields[prop]))
    return undefined
  return { owner: fields[prop], key: "value" }
}

/** Runs in the always-mounted Record form, independently of field-panel visibility. */
export function syncPreviewFileEvent(
  event: string,
  payload: FileEventPayload,
  fieldModel: Record<string, any>,
  onChange: (change: IFieldChangePayload) => void,
): boolean {
  if (!event.startsWith("preview-file-"))
    return false

  const target = previewFileTarget(fieldModel, payload)
  if (!target)
    return false

  const change = previewFileFieldChange(event, payload, target.owner[target.key])
  if (!change)
    return false
  onChange(change)
  return true
}

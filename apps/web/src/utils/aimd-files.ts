import type { UploadFileInfo } from "naive-ui"

/** Adapt authorized attachment metadata to the upload widget; never change the source value. */
export function normalizeAimdUploadFiles(value: unknown): UploadFileInfo[] {
  const items = Array.isArray(value) ? value : [value]
  return items.filter((item): item is Record<string, unknown> => !!item && typeof item === "object").map(item => ({
    ...item,
    id: typeof item.id === "string" ? item.id : item.airalogy_file_id,
    name: typeof item.name === "string" && item.name ? item.name : item.filename,
  })) as UploadFileInfo[]
}

export function aimdFileReference(value: unknown): string | undefined {
  const item = Array.isArray(value) ? value[0] : value
  const reference = typeof item === "string" ? item : item && typeof item === "object" ? (item as Record<string, unknown>).airalogy_file_id : undefined
  return typeof reference === "string" && reference.startsWith("airalogy.id.file.") ? reference : undefined
}

/** Resolve display metadata only while the same field request and FileId remain current. */
export async function loadCurrentAimdFileMetadata<T extends { airalogy_file_id?: string }>(
  currentValue: () => unknown,
  resolve: (reference: string) => Promise<T | null | undefined>,
  active: () => boolean,
): Promise<T | undefined> {
  const reference = aimdFileReference(currentValue())
  if (!reference)
    return undefined
  const data = await resolve(reference)
  return active() && aimdFileReference(currentValue()) === reference && data?.airalogy_file_id === reference ? data : undefined
}

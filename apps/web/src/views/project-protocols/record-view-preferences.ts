export const RECORD_PAGE_SIZE_OPTIONS = [5, 10, 20, 50] as const

const DEFAULT_RECORD_PAGE_SIZE = 10
const STORAGE_PREFIX = "airalogy:record-view"

function getUserScope(userId?: string) {
  return userId?.trim() || "guest"
}

function getStorage() {
  if (typeof window === "undefined") {
    return null
  }

  try {
    return window.localStorage
  }
  catch {
    return null
  }
}

function readStorageItem(key: string) {
  try {
    return getStorage()?.getItem(key) ?? null
  }
  catch {
    return null
  }
}

function writeStorageItem(key: string, value: string) {
  try {
    getStorage()?.setItem(key, value)
  }
  catch {
    // Preferences are optional and must not prevent the record view from working.
  }
}

function getPageSizeKey(userId?: string) {
  return `${STORAGE_PREFIX}:${getUserScope(userId)}:page-size`
}

function getFieldKeysKey(userId: string | undefined, protocolId: string) {
  return `${STORAGE_PREFIX}:${getUserScope(userId)}:protocol:${protocolId}:field-keys`
}

function getMetadataColumnKeysKey(userId: string | undefined, protocolId: string) {
  return `${STORAGE_PREFIX}:${getUserScope(userId)}:protocol:${protocolId}:metadata-column-keys`
}

function parseStringArray(value: string | null) {
  if (value === null) {
    return undefined
  }

  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed)
      ? [...new Set(parsed.filter((item): item is string => typeof item === "string" && item.length > 0))]
      : undefined
  }
  catch {
    return undefined
  }
}

export function getRecordPageSizePreference(userId?: string) {
  const value = Number(readStorageItem(getPageSizeKey(userId)))
  return RECORD_PAGE_SIZE_OPTIONS.includes(value as typeof RECORD_PAGE_SIZE_OPTIONS[number])
    ? value
    : DEFAULT_RECORD_PAGE_SIZE
}

export function setRecordPageSizePreference(userId: string | undefined, pageSize: number) {
  if (!RECORD_PAGE_SIZE_OPTIONS.includes(pageSize as typeof RECORD_PAGE_SIZE_OPTIONS[number])) {
    return
  }

  writeStorageItem(getPageSizeKey(userId), String(pageSize))
}

export function getRecordFieldKeysPreference(userId: string | undefined, protocolId: string) {
  if (!protocolId) {
    return []
  }

  return parseStringArray(readStorageItem(getFieldKeysKey(userId, protocolId))) ?? []
}

export function setRecordFieldKeysPreference(
  userId: string | undefined,
  protocolId: string,
  fieldKeys: string[],
) {
  if (!protocolId || fieldKeys.length === 0) {
    return
  }

  writeStorageItem(
    getFieldKeysKey(userId, protocolId),
    JSON.stringify([...new Set(fieldKeys)]),
  )
}

export function getRecordMetadataColumnKeysPreference(
  userId: string | undefined,
  protocolId: string,
) {
  if (!protocolId) {
    return undefined
  }

  return parseStringArray(readStorageItem(getMetadataColumnKeysKey(userId, protocolId)))
}

export function setRecordMetadataColumnKeysPreference(
  userId: string | undefined,
  protocolId: string,
  metadataColumnKeys: string[] | undefined,
) {
  if (!protocolId || metadataColumnKeys === undefined) {
    return
  }

  writeStorageItem(
    getMetadataColumnKeysKey(userId, protocolId),
    JSON.stringify([...new Set(metadataColumnKeys)]),
  )
}

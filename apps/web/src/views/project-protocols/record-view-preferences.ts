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

  try {
    const value = JSON.parse(readStorageItem(getFieldKeysKey(userId, protocolId)) || "[]")
    return Array.isArray(value)
      ? [...new Set(value.filter((item): item is string => typeof item === "string" && item.length > 0))]
      : []
  }
  catch {
    return []
  }
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

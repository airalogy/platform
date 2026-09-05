import type { IRecordData } from "@airalogy/aimd-core/types"
import { localStg } from "@/utils/storage"
import { cloneDeep as _cloneDeep } from "lodash-es"
import { toRaw } from "vue"

export interface RecordDraft<T = Partial<IRecordData>> {
  protocolId: string
  data: T
  timestamp: number
}

type StoredRecordDraft<T = Partial<IRecordData>> = Omit<RecordDraft<T>, "protocolId">
type DraftStorage = Record<string, Record<string, StoredRecordDraft<any>>>

/** Empty form initialization is not outstanding work; keep 0 and false as data. */
export function hasRecordDraftContent(value: unknown): boolean {
  if (value === null || value === undefined)
    return false
  if (typeof value === "string")
    return Boolean(value.trim())
  if (Array.isArray(value))
    return value.some(hasRecordDraftContent)
  if (typeof value === "object") {
    return Object.values(value).some(hasRecordDraftContent)
  }
  return true
}

function normalizeUserDraft(raw: unknown): Record<string, StoredRecordDraft> {
  if (!raw || typeof raw !== "object") {
    return {}
  }

  if (Array.isArray(raw)) {
    const result: Record<string, StoredRecordDraft> = {}
    for (const key of Object.keys(raw)) {
      const value = raw[Number(key)] as StoredRecordDraft | undefined
      if (value) {
        result[String(key)] = value
      }
    }
    return result
  }

  return raw as Record<string, StoredRecordDraft>
}

function readDraftStorage(): { storage: DraftStorage, migrated: boolean } {
  const raw = localStg.get("unitRecordDraft")
  if (!raw || typeof raw !== "object") {
    return { storage: {}, migrated: false }
  }

  let migrated = false
  if (Array.isArray(raw)) {
    migrated = true
  }

  const storage: DraftStorage = {}
  for (const [userKey, userDraft] of Object.entries(raw as Record<string, unknown>)) {
    if (Array.isArray(userDraft)) {
      migrated = true
    }
    storage[userKey] = normalizeUserDraft(userDraft)
  }

  if (migrated) {
    localStg.set("unitRecordDraft", storage)
  }
  return { storage, migrated }
}

export function listRecordDrafts(userId: string | number): RecordDraft[] {
  const { storage } = readDraftStorage()
  const drafts = storage[String(userId)] || {}
  return Object.entries(drafts)
    .filter(([, draft]) => draft && hasRecordDraftContent(draft.data))
    .map(([protocolId, draft]) => ({ protocolId, ...draft }))
    .sort((a, b) => b.timestamp - a.timestamp)
}

export function getRecordDraft<T = Partial<IRecordData>>(
  userId: string | number,
  protocolId: string | number,
): RecordDraft<T> | null {
  const draft = listRecordDrafts(userId).find(item => item.protocolId === String(protocolId))
  return draft as RecordDraft<T> | undefined || null
}

export function saveRecordDraft<T>(
  userId: string | number,
  protocolId: string | number,
  data: T,
): RecordDraft<T> {
  const { storage } = readDraftStorage()
  const userKey = String(userId)
  const protocolKey = String(protocolId)
  const draft = {
    data: _cloneDeep(toRaw(data)) as T,
    timestamp: Date.now(),
  }

  storage[userKey] ||= {}
  storage[userKey][protocolKey] = draft
  localStg.set("unitRecordDraft", storage)
  return { protocolId: protocolKey, ...draft }
}

export function deleteRecordDraft(userId: string | number, protocolId: string | number) {
  const { storage } = readDraftStorage()
  const userKey = String(userId)
  if (!storage[userKey]) {
    return
  }

  delete storage[userKey][String(protocolId)]
  if (Object.keys(storage[userKey]).length === 0) {
    delete storage[userKey]
  }
  localStg.set("unitRecordDraft", storage)
}

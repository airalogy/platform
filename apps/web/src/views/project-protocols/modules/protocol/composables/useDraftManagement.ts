import type { IRecordData } from "@airalogy/aimd-core/types"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { MaybeRefOrGetter, Ref } from "vue"
import { schemaCustomizer } from "@/service/api/project-protocols"
import { useAuthStore } from "@/store/modules/auth"
import { localStg } from "@/utils/storage"

import { extractAssetId } from "@/views/project-protocols/utils"
import { useClosableMessage } from "@airalogy/composables"
import { formatDate } from "@airalogy/shared/utils"
import { cloneDeep as _cloneDeep, get as _get, mergeWith as _mergeWith } from "lodash-es"
import { toRaw } from "vue"

// Draft data structure
export interface IDraftData<T = any> {
  data: T
  timestamp: number
}

interface SaveDraftOptions {
  silent?: boolean
}

export function useDraftManagement(
  protocol: MaybeRefOrGetter<ProtocolModels.ProtocolInfo | null | undefined>,
  recordData: Ref<Partial<IRecordData>>,
) {
  // const draftEventBus = useEventBus<"restore-draft", Record<string, Record<string, string | number>>>(draftEventKey)
  const message = useClosableMessage()
  const authStore = useAuthStore()

  type DraftStorage = Record<string, Record<string, IDraftData>>

  function normalizeUserDraft(raw: unknown): Record<string, IDraftData> {
    if (!raw || typeof raw !== "object") {
      return {}
    }

    if (Array.isArray(raw)) {
      const result: Record<string, IDraftData> = {}
      for (const key of Object.keys(raw)) {
        const value = raw[Number(key)] as IDraftData | undefined
        if (value) {
          result[String(key)] = value
        }
      }
      return result
    }

    return raw as Record<string, IDraftData>
  }

  function normalizeDraftStorage(raw: unknown): { storage: DraftStorage, migrated: boolean } {
    if (!raw || typeof raw !== "object") {
      return { storage: {}, migrated: false }
    }

    let migrated = false

    if (Array.isArray(raw)) {
      migrated = true
      const result: DraftStorage = {}
      for (const key of Object.keys(raw)) {
        result[String(key)] = normalizeUserDraft(raw[Number(key)])
      }
      return { storage: result, migrated }
    }

    const result: DraftStorage = {}
    for (const [userKey, userDraft] of Object.entries(raw as Record<string, unknown>)) {
      const normalizedUserDraft = normalizeUserDraft(userDraft)
      if (normalizedUserDraft !== userDraft) {
        migrated = true
      }
      result[userKey] = normalizedUserDraft
    }

    return { storage: result, migrated }
  }

  /**
   * Retrieves draft data for the specified protocol
   * @param protocolId - Protocol identifier
   * @returns Draft data or null if not found
   */
  function getDraft<T = any>(protocolId: string | number): IDraftData<T> | null {
    const userId = authStore.userInfo.id
    if (!userId || !protocolId) {
      return null
    }

    const rawStorage = localStg.get("unitRecordDraft")
    const { storage, migrated } = normalizeDraftStorage(rawStorage)

    const userKey = String(userId)
    const protocolKey = String(protocolId)
    const draft = _get(storage, [userKey, protocolKey], null) as IDraftData<T> | null

    if (migrated) {
      localStg.set("unitRecordDraft", storage as any)
    }

    return draft
  }

  /**
   * Saves draft data for the specified protocol
   * @param protocolId - Protocol identifier
   * @param data - Data to be saved
   */
  function saveDraft<T = any>(protocolId: string | number, data: T, options: SaveDraftOptions = {}): void {
    const userId = authStore.userInfo.id
    const shouldNotify = !options.silent
    if (!userId || !protocolId) {
      if (shouldNotify) {
        message.error("Failed to save draft: missing user or protocol info.")
      }
      return
    }

    try {
      const rawStorage = localStg.get("unitRecordDraft")
      const { storage } = normalizeDraftStorage(rawStorage)
      const userKey = String(userId)
      const protocolKey = String(protocolId)

      const payload = _cloneDeep(toRaw(data)) as T
      const currentDraft: IDraftData<T> = { data: payload, timestamp: Date.now() }

      if (!storage[userKey]) {
        storage[userKey] = {}
      }

      storage[userKey][protocolKey] = currentDraft

      localStg.set("unitRecordDraft", storage as any)
      if (shouldNotify) {
        message.success("Draft saved.")
      }
    }
    catch (error) {
      console.error("Failed to save draft:", error)
      if (shouldNotify) {
        message.error("Failed to save draft data.")
      }
    }
  }

  function prepareRestoreDraft<T = Partial<IRecordData>>(
    protocolId: string | number,
    mergeMode = false,
    shouldDelete = false,
  ): T | null {
    const currentDraft = getDraft(protocolId)?.data
    if (!currentDraft) {
      return null
    }

    if (shouldDelete) {
      deleteDraft(protocolId)
    }

    if (mergeMode) {
      return _mergeWith(currentDraft, recordData.value, schemaCustomizer) as T | null
    }
    else {
      return extractAssetId(currentDraft)
    }
  }

  /**
   * Deletes draft data for the specified protocol
   * @param protocolId - Protocol identifier
   */
  function deleteDraft(protocolId: string | number): void {
    const userId = authStore.userInfo.id
    if (!userId || !protocolId) {
      return
    }

    const rawStorage = localStg.get("unitRecordDraft")
    const { storage } = normalizeDraftStorage(rawStorage)

    const userKey = String(userId)
    const protocolKey = String(protocolId)

    if (!storage[userKey]) {
      return
    }

    delete storage[userKey][protocolKey]

    if (Object.keys(storage[userKey]).length === 0) {
      delete storage[userKey]
    }

    localStg.set("unitRecordDraft", storage as any)
  }

  /**
   * Formats the last modified timestamp of a draft
   * @param draft - Draft data
   * @returns Formatted timestamp string
   */
  function formatLastModified(draft: IDraftData | null): string {
    return formatDate(draft?.timestamp || 0, "date-time")
  }

  /**
   * Restores draft data by directly merging with existing recordData
   * This approach is simpler and more reliable than manual field processing
   */
  // function handleRestoreDraft(data: IRecordData) {
  //   try {
  //     // Validate input data
  //     if (!data || typeof data !== "object") {
  //       console.warn("Invalid draft data for restoration:", data)
  //       message.warning("Draft data is invalid")
  //       return
  //     }

  //     // Directly merge draft data with existing recordData
  //     // The field structure parsing will handle data transformation automatically
  //     Object.entries(data).forEach(([scope, fields]) => {
  //       if (!isObject(fields)) {
  //         console.warn(`Skipping invalid scope data for '${scope}':`, fields)
  //         return
  //       }

  //       // Ensure scope exists in recordData
  //       if (!recordData.value[scope as IRecordDataKey]) {
  //         recordData.value[scope as IRecordDataKey] = {}
  //       }

  //       // Merge fields into the scope
  //       Object.entries(fields as Record<string, any>).forEach(([key, value]) => {
  //         try {
  //           // For file references, preserve the structure and let the field system handle loading
  //           if (value && typeof value === "object" && value.airalogy_file_id) {
  //             recordData.value[scope as IRecordDataKey][key] = value
  //             console.debug(`Restored file reference for ${scope}.${key}:`, value.airalogy_file_id)
  //           }
  //           else {
  //             // For other data types, merge directly
  //             recordData.value[scope as IRecordDataKey][key] = value
  //           }
  //         }
  //         catch (fieldError) {
  //           console.error(`Error restoring field ${scope}.${key}:`, fieldError)
  //           // Continue with other fields even if one fails
  //         }
  //       })
  //     })

  //     // Emit a general field update event to trigger re-processing
  //     fieldEventBus.emit("draft-restored", { data, mode: "merge" })
  //     console.debug("Draft restoration completed successfully")
  //   }
  //   catch (error) {
  //     console.error("Error restoring draft:", error)
  //     message.error("Failed to restore draft data")
  //   }
  // }

  /**
   * Replaces current data with draft data
   * This approach is simpler and more reliable than manual field processing
   */
  // function handleReplaceDraft(data: IRecordData) {
  //   try {
  //     // Validate input data
  //     if (!data || typeof data !== "object") {
  //       console.warn("Invalid draft data for replacement:", data)
  //       message.warning("Draft data is invalid")
  //       return
  //     }

  //     // Clear existing data and replace with draft data
  //     Object.keys(recordData.value).forEach((scope) => {
  //       recordData.value[scope as IRecordDataKey] = {}
  //     })

  //     // Set draft data directly
  //     Object.entries(data).forEach(([scope, fields]) => {
  //       if (!isObject(fields)) {
  //         console.warn(`Skipping invalid scope data for '${scope}':`, fields)
  //         return
  //       }

  //       try {
  //         recordData.value[scope as IRecordDataKey] = { ...fields as Record<string, any> }
  //       }
  //       catch (scopeError) {
  //         console.error(`Error replacing scope ${scope}:`, scopeError)
  //         // Initialize empty scope if replacement fails
  //         recordData.value[scope as IRecordDataKey] = {}
  //       }
  //     })

  //     // Emit a general field update event to trigger re-processing
  //     fieldEventBus.emit("draft-restored", { data, mode: "replace" })
  //     console.debug("Draft replacement completed successfully")
  //   }
  //   catch (error) {
  //     console.error("Error replacing with draft:", error)
  //     message.error("Failed to replace with draft data")
  //   }
  // }

  return {
    getDraft,
    saveDraft,
    prepareRestoreDraft,
    deleteDraft,
    formatLastModified,
  }
}

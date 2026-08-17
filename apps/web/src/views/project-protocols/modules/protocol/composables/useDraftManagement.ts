import type { IRecordData } from "@airalogy/aimd-core/types"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { MaybeRefOrGetter, Ref } from "vue"
import { schemaCustomizer } from "@/service/api/project-protocols"
import { useAuthStore } from "@/store/modules/auth"
import { deleteRecordDraft, getRecordDraft, saveRecordDraft } from "@/utils/recordDrafts"

import { extractAssetId } from "@/views/project-protocols/utils"
import { useClosableMessage } from "@airalogy/composables"
import { formatDate } from "@airalogy/shared/utils"
import { mergeWith as _mergeWith } from "lodash-es"

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

    const draft = getRecordDraft<T>(userId, protocolId)
    return draft ? { data: draft.data, timestamp: draft.timestamp } : null
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
      saveRecordDraft(userId, protocolId, data)
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

    deleteRecordDraft(userId, protocolId)
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

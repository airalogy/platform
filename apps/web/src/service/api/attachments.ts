import { AIRALOGY_FILE_ID_PREFIX, parseAiralogyId } from "@airalogy/shared/utils"
import { request } from "../request"
import { getReferenceAssets, postUploadReferenceAssets } from "./project-protocols"

interface CachedAttachment {
  data: Api.Attachment.AttachmentItem | Promise<Api.Attachment.AttachmentItem | null>
  expiresAt: number
  isLoading: boolean
  lastAccessed: number
}
export const cachedAttachments = new Map<string, CachedAttachment>()

export async function getAttachments(id: string | number) {
  if (!id) {
    throw new Error("id is required")
  }

  let reqId = id

  if (typeof id === "string" && id.startsWith(AIRALOGY_FILE_ID_PREFIX)) {
    const parsed = parseAiralogyId(id)
    if (parsed?.type === "file") {
      // Use getReferenceAssets for AIRALOGY_FILE_ID_PREFIX IDs
      // Pass only the UUID part (without prefix) to getReferenceAssets
      const uuid = parsed.uuid

      // Try to fetch using getReferenceAssets (which uses /airalogy_files/{uuid})
      // We pass false to showError to handle errors gracefully if needed
      const res = await getReferenceAssets(uuid, false)

      if (res.data) {
        return res
      }

      // If failed (e.g. 404/400), fallback to /attachments/{uuid}
      // This handles cases where the file might be in standard attachments but referenced with airalogy ID prefix
      reqId = parsed.uuid
    }
    else {
      // fallback to original id if parsing fails
      reqId = id
    }
  }

  return await request<Api.Attachment.AttachmentItem>({
    url: `/attachments/${reqId}`,
    method: "GET",
  })
}

export async function postAddAttachments(file: File, protocolId?: string | null) {
  if (!file) {
    throw new Error("file is required")
  }

  let res

  if (protocolId) {
    res = await postUploadReferenceAssets(protocolId, { file })
  }
  else {
    const formData = new FormData()
    formData.append("file", file)

    res = await request<Api.Attachment.AttachmentItem>({
      url: "/attachments/",
      method: "POST",
      data: formData,
    })
  }

  if (res.data && res.data.id) {
    const now = Date.now()
    // Cache under UUID key if possible
    let cacheKey = res.data.id
    if (typeof cacheKey === "string" && cacheKey.startsWith(AIRALOGY_FILE_ID_PREFIX)) {
      const parsed = parseAiralogyId(cacheKey)
      if (parsed?.type === "file") {
        cacheKey = parsed.uuid
      }
    }

    cachedAttachments.set(cacheKey, {
      data: res.data,
      expiresAt: now + 60000, // 1 minute
      isLoading: false,
      lastAccessed: now,
    })
  }

  return res
}

export async function deleteAttachment(id: string) {
  if (!id) {
    throw new Error("id is required")
  }

  let uuid = id
  if (typeof id === "string" && id.startsWith(AIRALOGY_FILE_ID_PREFIX)) {
    const parsed = parseAiralogyId(id)
    if (parsed?.type === "file") {
      uuid = parsed.uuid
    }
  }

  if (!uuid) {
    throw new Error("Invalid id")
  }

  const { data, error } = await request<{ message: string }>({
    url: `/attachments/${uuid}`,
    method: "DELETE",
  })

  if (data && data.message === "success") {
    cachedAttachments.delete(uuid)
    return true
  }

  return false
}

function cleanupCache() {
  const now = Date.now()

  cachedAttachments.forEach((entry, id) => {
    if (entry.expiresAt < now && !entry.isLoading) {
      cachedAttachments.delete(id)
    }
  })
}

export async function getCachedAttachment(id: string) {
  let lookupId = id
  if (typeof id === "string" && id.startsWith(AIRALOGY_FILE_ID_PREFIX)) {
    const parsed = parseAiralogyId(id)
    if (parsed?.type === "file") {
      lookupId = parsed.uuid
    }
  }

  // Check if we have a valid cache entry
  const cached = cachedAttachments.get(lookupId)
  const now = Date.now()

  // If we have a valid, non-expired cache entry, return it
  if (cached && cached.expiresAt > now && !cached.isLoading) {
    // Update last accessed time
    cached.lastAccessed = now
    return cached.data as Api.Attachment.AttachmentItem
  }

  // If there's a pending request in progress, wait for it
  if (cached?.isLoading) {
    try {
      // The data is already a Promise when isLoading is true
      const result = await cached.data
      if (result) {
        cached.lastAccessed = now
      }
      return result
    }
    catch (error) {
      console.error("Error while waiting for pending attachment request:", error)
      cachedAttachments.delete(lookupId)
      return null
    }
  }

  // Clean up cache if needed
  cleanupCache()

  // No valid cache - fetch new data
  // We must pass the ORIGINAL id to getAttachments so it can decide whether to use getReferenceAssets
  const promise = getAttachments(id).then((res) => {
    if (res.data) {
      // Cache the result for 1 minute
      cachedAttachments.set(lookupId, {
        data: res.data,
        expiresAt: now + 60000, // 1 minute
        isLoading: false,
        lastAccessed: now,
      })
      return res.data
    }
    return null
  }).catch((error) => {
    console.error("Error fetching attachment data:", error)
    cachedAttachments.delete(lookupId)
    return null
  })

  // Store the promise in cache while loading
  cachedAttachments.set(lookupId, {
    data: promise,
    expiresAt: now + 30000, // 30 seconds max for loading state
    isLoading: true,
    lastAccessed: now,
  })

  return await promise
}

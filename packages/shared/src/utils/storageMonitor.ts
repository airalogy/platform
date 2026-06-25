/**
 * Storage monitoring utilities to help prevent QuotaExceededError
 */

interface StorageInfo {
  used: number
  total: number
  available: number
  usagePercentage: number
}

/**
 * Gets storage quota information (when available)
 */
export async function getStorageQuota(): Promise<StorageInfo | null> {
  try {
    if ("storage" in navigator && "estimate" in navigator.storage) {
      const estimate = await navigator.storage.estimate()
      const used = estimate.usage || 0
      const total = estimate.quota || 0
      const available = total - used
      const usagePercentage = total > 0 ? (used / total) * 100 : 0

      return { used, total, available, usagePercentage }
    }
  }
  catch (error) {
    console.warn("Storage quota estimation not available:", error)
  }

  return null
}

/**
 * Formats bytes to human readable string
 */
export function formatBytes(bytes: number): string {
  if (bytes === 0)
    return "0 Bytes"

  const k = 1024
  const sizes = ["Bytes", "KB", "MB", "GB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))

  return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`
}

/**
 * Checks if storage is approaching quota limits
 */
export async function checkStorageWarning(): Promise<{
  shouldWarn: boolean
  message: string
  storageInfo: StorageInfo | null
}> {
  const storageInfo = await getStorageQuota()

  if (!storageInfo) {
    return {
      shouldWarn: false,
      message: "Storage quota monitoring not available",
      storageInfo: null,
    }
  }

  const { usagePercentage, available, used, total } = storageInfo

  if (usagePercentage > 90) {
    return {
      shouldWarn: true,
      message: `Storage is ${usagePercentage.toFixed(1)}% full (${formatBytes(used)} of ${formatBytes(total)}). Consider clearing browser data.`,
      storageInfo,
    }
  }

  if (usagePercentage > 75) {
    return {
      shouldWarn: true,
      message: `Storage is ${usagePercentage.toFixed(1)}% full (${formatBytes(available)} remaining). Large files will be stored on server.`,
      storageInfo,
    }
  }

  return {
    shouldWarn: false,
    message: `Storage: ${formatBytes(used)} of ${formatBytes(total)} used (${usagePercentage.toFixed(1)}%)`,
    storageInfo,
  }
}

/**
 * Logs detailed storage information for debugging
 */
export async function logStorageDetails(context: string = "Storage Monitor"): Promise<void> {
  const storageInfo = await getStorageQuota()

  if (storageInfo) {
    console.log(`[${context}] Storage Details:`, {
      used: formatBytes(storageInfo.used),
      total: formatBytes(storageInfo.total),
      available: formatBytes(storageInfo.available),
      usagePercentage: `${storageInfo.usagePercentage.toFixed(2)}%`,
    })
  }
  else {
    console.log(`[${context}] Storage quota information not available`)
  }
}

/**
 * Estimates size of data before storing
 */
export function estimateDataSize(data: any): { sizeInBytes: number, sizeFormatted: string } {
  const jsonString = JSON.stringify(data)
  const sizeInBytes = new Blob([jsonString]).size

  return {
    sizeInBytes,
    sizeFormatted: formatBytes(sizeInBytes),
  }
}

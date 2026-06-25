import { request } from "../request"

/**
 * Fetch CSV content from a URL
 * @param url - The URL to fetch CSV content from
 * @param requestId - Optional request ID for tracking
 * @returns Promise with CSV content as string
 */
export async function fetchCsvContent(url: string, requestId?: string) {
  if (!url) {
    throw new Error("URL is required")
  }

  const { data, error } = await request<string, "text">({
    url,
    method: "GET",
    responseType: "text" as const,
    metadata: {
      requestId,
      showError: false, // Handle errors in the component
    },
  })

  if (error) {
    throw new Error(`Failed to fetch CSV content: ${error.message}`)
  }

  return data
}

/**
 * Fetch text content from a URL
 * @param url - The URL to fetch text content from
 * @param requestId - Optional request ID for tracking
 * @returns Promise with text content as string
 */
export async function fetchBlobContent(url: string, requestId?: string) {
  if (!url) {
    throw new Error("URL is required")
  }

  const { data, error } = await request<Blob, "blob">({
    url,
    method: "GET",
    responseType: "blob",
    metadata: {
      requestId,
      showError: false, // Handle errors in the component
    },
  })

  if (error) {
    throw new Error(`Failed to fetch text content: ${error.message}`)
  }

  return data
}

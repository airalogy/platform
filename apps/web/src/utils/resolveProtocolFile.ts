import { getStaticResearchAssets } from "@/service/api/project-protocols"

/**
 * Resolve relative file paths to absolute URLs for protocol assets
 * @param src - The source path (e.g., "files/image.png", "assets/video.mp4")
 * @param protocolId - The protocol ID to fetch assets from
 * @returns Promise with URL or null if resolution fails
 */
export async function resolveProtocolFile(
  src: string,
  protocolId: string | number,
): Promise<{ url: string } | null> {
  if (!src || !protocolId) {
    return null
  }

  // Check if it's a relative path (not absolute URL, not data URI)
  // Includes paths starting with / (relative to protocol root)
  const isRelativePath = !src.startsWith("http://")
    && !src.startsWith("https://")
    && !src.startsWith("data:")
    && !src.startsWith("blob:")

  if (isRelativePath) {
    try {
      // Use the relative path as-is
      const response = await getStaticResearchAssets(protocolId, src)

      if (response?.data?.url) {
        return { url: response.data.url }
      }
    }
    catch (error) {
      console.error("Failed to resolve file:", src, error)
    }
  }

  return null
}

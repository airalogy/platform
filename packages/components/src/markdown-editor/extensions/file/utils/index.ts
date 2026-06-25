import type { Editor, InputRuleFinder, InputRuleMatch, PasteRuleFinder } from "@tiptap/core"
import type { CustomImageOptions } from "../image/types"
import type { FileUploadOptions, UploadReturnType } from "../types"
import { fileToBlob, getFileExtensionFromBasename } from "@airalogy/shared"
import { AIRALOGY_FILE_ID_REG } from "@airalogy/shared/constants"
import { getAiralogyFileId } from "@airalogy/shared/utils/parseAiralogyId"

/**
 * Parses an airalogy file URL into its components
 */
export function parseAiralogyFileUrl(url: string): { airalogyId: string, extension: string } | null {
  const airalogyMatch = url.match(AIRALOGY_FILE_ID_REG)
  if (!airalogyMatch)
    return null

  return {
    airalogyId: url,
    extension: airalogyMatch[2],
  }
}

/**
 * Matches both airalogy.id.file format and data URLs
 */
export const inputFinder: InputRuleFinder = (text: string) => {
  // Basic image markdown pattern
  const imageStart = text.match(/(?:^|\s)!\[([^\]]*)\]\(([^)]+)\)/)
  if (!imageStart) {
    return null
  }

  const fullMatch = imageStart[0] || ""
  const alt = imageStart[1] || ""
  const src = imageStart[2] || ""

  // Check if it's either an airalogy file or data URL
  const isAiralogyFile = src.startsWith("airalogy.id.file.")
  const isDataUrl = src.startsWith("data:")

  if (!isAiralogyFile && !isDataUrl)
    return null

  // Extract title if present
  const titleMatch = src.match(/\s+"([^"]+)"$/)
  const title = titleMatch ? titleMatch[1] : ""

  // Clean up the src by removing title
  const cleanSrc = titleMatch ? src.slice(0, titleMatch.index).trim() : src.trim()

  // Parse airalogy file info if present
  let airalogyId: string | undefined
  let extension: string | undefined
  let filename: string | undefined
  if (isAiralogyFile) {
    const parsed = parseAiralogyFileUrl(cleanSrc)
    if (parsed) {
      airalogyId = parsed.airalogyId
      extension = parsed.extension
    }
  }

  return {
    text: fullMatch,
    index: imageStart.index || 0,
    match: [fullMatch, alt, cleanSrc, title],
    data: {
      alt,
      src: cleanSrc,
      title,
      isDataUrl,
      airalogyId,
      extension,
      filename,
    },
  } satisfies InputRuleMatch
}

/**
 * Matches both airalogy.id.file format and data URLs for paste events
 */
export const pasteFinder: PasteRuleFinder = (text: string) => {
  const match = inputFinder(text)
  return match ? [match] : null
}

export function getMatchAttributes(match: InputRuleMatch) {
  if (!match.data)
    return null

  const { alt, src, title, isDataUrl, airalogyId, extension } = match.data

  if (isDataUrl) {
    return {
      src,
      alt,
      title: title || null,
    }
  }

  if (airalogyId && extension) {
    return {
      src,
      alt,
      title: title || null,
      airalogyId,
      extension,
    }
  }

  return null
}

export async function defaultUploadFn(file: File, editor: Editor, options: FileUploadOptions | CustomImageOptions): Promise<UploadReturnType> {
  if (!editor) {
    return null
  }

  const protocolId = options.protocolId
  // Start upload
  try {
    const url = await fileToBlob(file)
    if (!url) {
      return null
    }

    const ext = getFileExtensionFromBasename(file.name)

    const res = await options.postAddAttachments?.(file, protocolId)
    if (!res) {
      return null
    }

    // Handle response wrapper from apps/web
    const data = (res && typeof res === "object" && "data" in res) ? res.data : res

    if (!data) {
      return null
    }

    // Use server URL if available, fallback to blob URL
    const src = data.url || url

    return {
      airalogyId: ext ? getAiralogyFileId(data.id, ext)! : data.id,
      id: data.id,
      src,
      filename: data.filename,
    }
  }
  catch (error) {
    options.onUploadError?.(error instanceof Error ? error : new Error(String(error)))

    return null
  }
}

/**
 * File and Base64 helper utilities
 * Migrated from markdown-it/utils.ts
 */

/**
 * File error interface
 */
export interface FileError {
  file: File | string
  reason: "type" | "size" | "invalidBase64" | "base64NotAllowed"
}

/**
 * File validation options
 */
export interface FileValidationOptions {
  /**
   * Controls the allowed MIME types.
   * @default []
   * @example ["image/*", "application/pdf", "text/csv"]
   */
  allowedMimeTypes: string[]

  /**
   * Controls the maximum file size in bytes.
   * @default 0 (no limit)
   * @example 1024 * 1024 (1MB)
   */
  maxFileSize?: number
  /**
   * Controls if base64 images are allowed. Enable this if you want to allow
   * base64 image urls in the `src` attribute.
   * @default true
   * @example true
   */
  allowBase64: boolean
}

/**
 * File input type
 */
export type FileInput = File | {
  src: string | File
  alt?: string
  title?: string
  id: string
  extension?: string
  filename?: string
}

/**
 * Check if running in browser
 */
export const isClient = (): boolean => typeof window !== "undefined"

/**
 * Check if running on server
 */
export const isServer = (): boolean => !isClient()

/**
 * Check if running on macOS
 */
export const isMacOS = (): boolean => isClient() && window.navigator.platform === "MacIntel"

/**
 * Generate random ID
 */
export const randomId = (): string => Math.random().toString(36).slice(2, 11)

/**
 * Check if string is a valid URL
 */
export function isUrl(
  text: string,
  options: { requireHostname: boolean, allowBase64?: boolean } = { requireHostname: false },
): boolean {
  if (!text || text.includes("\n")) {
    return false
  }

  // Accept paths that start with a slash as valid URLs
  if (text.startsWith("/") && !options.requireHostname) {
    return true
  }

  try {
    const url = new URL(text)
    const blockedProtocols = [
      "javascript:",
      "file:",
      "vbscript:",
      ...(options.allowBase64 ? [] : ["data:"]),
    ]

    if (blockedProtocols.includes(url.protocol)) {
      return false
    }
    if (options.allowBase64 && url.protocol === "data:") {
      return isBase64(text)
    }
    if (url.hostname) {
      return true
    }

    return (
      url.protocol !== ""
      && (url.pathname.startsWith("//") || url.pathname.startsWith("http"))
      && !options.requireHostname
    )
  }
  catch {
    return false
  }
}

/**
 * Creates a full URL by adding a hostname to a relative path
 */
export function createFullUrl(path: string, baseUrl?: string): string {
  if (!path) {
    return ""
  }

  // If already a full URL, return as is
  if (isUrl(path, { requireHostname: true }) || path.startsWith("data:")) {
    return path
  }

  // If it's a relative path starting with '/', add the base URL
  if (path.startsWith("/")) {
    const base = baseUrl || (isClient() ? window.location.origin : "")
    return `${base}${path}`
  }

  // Otherwise, assume it's a relative URL without a leading slash
  return baseUrl
    ? `${baseUrl}/${path}`
    : (isClient() ? `${window.location.origin}/${path}` : `/${path}`)
}

/**
 * Sanitize URL for security
 */
export function sanitizeUrl(
  url: string | null | undefined,
  options: { allowBase64?: boolean } = {},
): string | undefined {
  if (!url) {
    return undefined
  }

  if (options.allowBase64 && url.startsWith("data:image")) {
    return isUrl(url, { requireHostname: false, allowBase64: true }) ? url : undefined
  }
  return isUrl(url, { requireHostname: false, allowBase64: options.allowBase64 })
    || /^(?:\/|#|mailto:|sms:|fax:|tel:)/.test(url)
    ? url
    : `https://${url}`
}

/**
 * Check if string is base64 encoded
 */
export function isBase64(str: string): boolean {
  if (str.startsWith("data:")) {
    const matches = str.match(/^data:[^;]+;base64,(.+)$/)
    if (matches && matches[1]) {
      str = matches[1]
    }
    else {
      return false
    }
  }

  try {
    return btoa(atob(str)) === str
  }
  catch {
    return false
  }
}

/**
 * Get MIME type from base64 string
 */
export function base64MimeType(encoded: string): string {
  const result = encoded.match(/data:([a-zA-Z0-9]+\/[a-zA-Z0-9-.+]*),/)
  return result && result.length > 1 ? result[1] : "unknown"
}

/**
 * Convert blob URL to base64
 */
export async function blobUrlToBase64(blobUrl: string): Promise<string> {
  const response = await fetch(blobUrl)
  const blob = await response.blob()

  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result)
      }
      else {
        reject(new Error("Failed to convert Blob to base64"))
      }
    }
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}

/**
 * Convert file to base64
 */
export function fileToBase64(file: File | Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result)
      }
      else {
        reject(new Error("Failed to convert File to base64"))
      }
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

/**
 * Convert file to blob URL
 */
export function fileToBlob(file: File | Blob): string {
  return URL.createObjectURL(file)
}

/**
 * Convert buffer to blob
 */
export function bufferToBlob(buffer: Uint8Array<ArrayBufferLike>, type?: string) {
  return new Blob([buffer.buffer as BlobPart], { type })
}

/**
 * Convert base64 to buffer
 */
export function base64ToBuffer(base64: string) {
  const binaryString = window.atob(base64)
  const length = binaryString.length
  const buffer = new ArrayBuffer(length)
  const view = new Uint8Array(buffer)
  for (let i = 0; i < length; i++) {
    view[i] = binaryString.charCodeAt(i)
  }
  return buffer
}

/**
 * Convert blob URL to file
 */
export async function blobUrlToFile(blobUrl: string, fileName: string): Promise<File> {
  const response = await fetch(blobUrl)
  const blob = await response.blob()
  const file = new File([blob], fileName, { type: blob.type })

  return file
}

/**
 * Read file as data URL
 */
export function readFileDataUrl(file: File): Promise<any> {
  const reader = new FileReader()

  return new Promise((resolve, reject) => {
    reader.onload = readerEvent => resolve(readerEvent.target!.result)
    reader.onerror = reject

    reader.readAsDataURL(file)
  })
}

/**
 * Check type and size of file
 */
export function checkTypeAndSize(
  input: File | string,
  { allowedMimeTypes, maxFileSize }: FileValidationOptions,
): { isValidType: boolean, isValidSize: boolean } {
  const mimeType = input instanceof File ? input.type : base64MimeType(input)
  const size = input instanceof File ? input.size : atob(input.split(",")[1]).length

  const isValidType
    = allowedMimeTypes.length === 0
    || allowedMimeTypes.includes(mimeType)
    || allowedMimeTypes.includes(`${mimeType.split("/")[0]}/*`)

  const isValidSize = !maxFileSize || size <= maxFileSize

  return { isValidType, isValidSize }
}

/**
 * Validate file or base64
 */
export function validateFileOrBase64<T extends FileInput>(
  input: File | string,
  options: FileValidationOptions,
  originalFile: T,
  validFiles: T[],
  errors: FileError[],
): void {
  const { isValidType, isValidSize } = checkTypeAndSize(input, options)

  if (isValidType && isValidSize) {
    validFiles.push(originalFile)
  }
  else {
    if (!isValidType) {
      errors.push({ file: input, reason: "type" })
    }
    if (!isValidSize) {
      errors.push({ file: input, reason: "size" })
    }
  }
}

/**
 * Filter files by validation options
 */
export function filterFiles<T extends FileInput>(
  files: T[],
  options: FileValidationOptions,
): [T[], FileError[]] {
  const validFiles: T[] = []
  const errors: FileError[] = []

  files.forEach((file) => {
    const actualFile = "src" in file ? file.src : file

    if (actualFile instanceof File) {
      validateFileOrBase64(actualFile, options, file, validFiles, errors)
    }
    else if (typeof actualFile === "string") {
      if (isBase64(actualFile)) {
        if (options.allowBase64) {
          validateFileOrBase64(actualFile, options, file, validFiles, errors)
        }
        else {
          errors.push({ file: actualFile, reason: "base64NotAllowed" })
        }
      }
      else {
        if (!sanitizeUrl(actualFile, { allowBase64: options.allowBase64 })) {
          errors.push({ file: actualFile, reason: "invalidBase64" })
        }
        else {
          validFiles.push(file)
        }
      }
    }
  })

  return [validFiles, errors]
}

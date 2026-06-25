/**
 * Download data as a file
 * @param data - The data to download
 * @param filename - The filename to save as
 * @param type - The MIME type of the file
 */
export function downloadAs(data: BlobPart, filename: string, type = "application/json"): void {
  const blob = new Blob([data], { type })
  const url = URL.createObjectURL(blob)
  downloadAsUrl(url, filename)
  URL.revokeObjectURL(url)
}

/**
 * Download from URL
 * @param url - The URL to download from
 * @param filename - The filename to save as
 */
export function downloadAsUrl(url: string, filename: string): void {
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

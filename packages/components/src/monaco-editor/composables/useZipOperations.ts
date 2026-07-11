import type { DirectoryInterface } from "../types"
import { zipSync } from "fflate"
import { isDirectory, isFile } from "../utils"

export function useZipOperations() {
  const encoder = new TextEncoder()

  async function downloadAsZip(fileData: DirectoryInterface | DirectoryInterface[] | null) {
    if (!fileData)
      return

    const files = Array.isArray(fileData) ? fileData : [fileData]
    const zipData: Record<string, Uint8Array> = {}

    // Add files to zip
    files.forEach((file) => {
      if (isDirectory(file) && file.children) {
        // Recursively add directory contents
        addDirectoryToZip(file, "", zipData)
      }
      else if (isFile(file) && file.content) {
        if (typeof file.content === "string") {
          // Add file content
          zipData[file.name] = encoder.encode(file.content)
        }
        else {
          zipData[file.name] = file.content
        }
      }
    })

    // Generate zip file
    const zipBlob = new Blob([zipSync(zipData)], { type: "application/zip" })
    const url = URL.createObjectURL(zipBlob)

    // Trigger download
    const a = document.createElement("a")
    a.href = url
    a.download = "project.zip"
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  function addDirectoryToZip(
    dir: DirectoryInterface,
    parentPath: string,
    zipData: Record<string, Uint8Array>,
  ) {
    const currentPath = parentPath ? `${parentPath}/${dir.name}` : dir.name

    dir.children?.forEach((child) => {
      if (isDirectory(child) && child.children) {
        addDirectoryToZip(child, currentPath, zipData)
      }
      else if (isFile(child) && child.content) {
        const filePath = `${currentPath}/${child.name}`
        zipData[filePath] = typeof child.content === "string"
          ? encoder.encode(child.content)
          : child.content
      }
    })
  }

  return {
    downloadAsZip,
  }
}

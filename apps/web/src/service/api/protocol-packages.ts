import type { DirectoryInterface, FileInterface, FileSystemItem } from "@airalogy/components/monaco-editor/types"
import { countTotalFiles, isDirectory, isFile } from "@airalogy/components/src/monaco-editor/utils"
import { arrayBufferToString, FILE_TYPES } from "@airalogy/shared"
import { unzip, zipSync } from "fflate"
import { deleteAttachment, getAttachments, postAddAttachments } from "./attachments"

interface ProtocolPackage {
  packageId: string
  attachmentId: string
  metadata: {
    rootPath: string
    createdAt: string
    fileCount: number
    totalSize: number
  }
}

/**
 * Converts DirectoryInterface[] to a zip file and uploads to server
 */
export async function uploadProtocolPackage(
  packageId: string,
  fileData: DirectoryInterface[],
  rootPath: string,
  protocolId?: string,
): Promise<ProtocolPackage | null> {
  try {
    // Create zip file from file data
    const zipBlob = await createZipFromFileData(fileData, rootPath)

    // Create File object for upload
    const zipFile = new File([zipBlob], `${packageId}.zip`, {
      type: "application/zip",
    })

    // Upload to server using existing attachments API
    const response = await postAddAttachments(zipFile, protocolId)

    if (response.data) {
      const packageInfo: ProtocolPackage = {
        packageId,
        attachmentId: response.data.id,
        metadata: {
          rootPath,
          createdAt: new Date().toISOString(),
          fileCount: countTotalFiles(fileData),
          totalSize: zipBlob.size,
        },
      }

      // Store package metadata in localStorage (much smaller than file content)
      localStorage.setItem(`protocol-package-${packageId}`, JSON.stringify(packageInfo))

      return packageInfo
    }

    return null
  }
  catch (error) {
    console.error("Failed to upload protocol package:", error)
    throw error
  }
}

/**
 * Downloads and extracts protocol package from server
 */
export async function downloadProtocolPackage(packageId: string): Promise<FileSystemItem[] | null> {
  try {
    // Get package metadata
    const packageInfoStr = localStorage.getItem(`protocol-package-${packageId}`)
    if (!packageInfoStr) {
      throw new Error(`Package metadata not found for ${packageId}`)
    }

    const packageInfo: ProtocolPackage = JSON.parse(packageInfoStr)

    // Download attachment from server
    const response = await getAttachments(packageInfo.attachmentId)

    if (response.data?.url) {
      // Download the zip file
      const zipResponse = await fetch(response.data.url)
      const zipBlob = await zipResponse.blob()

      // Extract zip file back to DirectoryInterface[]
      const fileData = await extractZipToFileData(zipBlob, packageInfo.metadata.rootPath)

      return fileData
    }

    return null
  }
  catch (error) {
    console.error("Failed to download protocol package:", error)
    throw error
  }
}

/**
 * Deletes protocol package from server and local metadata
 */
export async function deleteProtocolPackage(packageId: string): Promise<boolean> {
  try {
    // Get package metadata
    const packageInfoStr = localStorage.getItem(`protocol-package-${packageId}`)
    if (!packageInfoStr) {
      return true // Already deleted
    }

    const packageInfo: ProtocolPackage = JSON.parse(packageInfoStr)

    // Delete from server
    await deleteAttachment(packageInfo.attachmentId)

    // Remove local metadata
    localStorage.removeItem(`protocol-package-${packageId}`)

    return true
  }
  catch (error) {
    console.error("Failed to delete protocol package:", error)
    return false
  }
}

/**
 * Creates a zip blob from DirectoryInterface array
 */
async function createZipFromFileData(fileData: DirectoryInterface[], rootPath: string): Promise<Blob> {
  const zipData: Record<string, Uint8Array> = {}
  const encoder = new TextEncoder()

  function addFilesToZip(items: FileSystemItem[], basePath = "") {
    for (const item of items) {
      const { name, path } = item
      const itemPath = basePath ? `${basePath}/${name}` : item.name

      if (isDirectory(item)) {
        if (item.children) {
          addFilesToZip(item.children, itemPath)
        }
        else {
          // Add empty directory
          zipData[`${itemPath}/`] = new Uint8Array(0)
        }
      }
      else if (isFile(item)) {
        const { content } = item
        if (content) {
          if (typeof content === "string") {
            // Text file content
            zipData[itemPath] = encoder.encode(content)
          }
          else {
            zipData[itemPath] = content
          }
        }
        else if (item.fileUrl) {
          // TODO: Binary file - need to fetch blob data
          // This is a limitation - we'd need to store binary data differently
          console.warn(`Binary file ${itemPath} cannot be zipped - fileUrl not accessible`)
        }
      }
    }
  }

  addFilesToZip(fileData)

  const compressed = zipSync(zipData)
  return new Blob([compressed], { type: "application/zip" })
}

/**
 * Extracts zip blob back to DirectoryInterface array
 */
async function extractZipToFileData(zipBlob: Blob, rootPath: string): Promise<FileSystemItem[]> {
  return new Promise((resolve, reject) => {
    const arrayBuffer = zipBlob.arrayBuffer()
    arrayBuffer.then((buffer) => {
      const uint8Array = new Uint8Array(buffer)

      unzip(uint8Array, (err, unzipped) => {
        if (err) {
          reject(new Error("Failed to extract zip file"))
          return
        }

        const fileData: FileSystemItem[] = []
        const pathMap = new Map<string, FileSystemItem>()

        // Create directory structure from unzipped files
        for (const [relativePath, fileBuffer] of Object.entries(unzipped)) {
          const pathParts = relativePath.split("/").filter(Boolean)

          // Create nested directory structure
          let currentPath = ""
          let currentLevel = fileData

          for (let i = 0; i < pathParts.length; i++) {
            const part = pathParts[i]
            currentPath = currentPath ? `${currentPath}/${part}` : part

            if (i === pathParts.length - 1) {
              // This is the file
              // TODO: do not decode binary content
              const isTextFile = FILE_TYPES.text.some(ext => currentPath.toLowerCase().endsWith(ext))
              const content = isTextFile ? arrayBufferToString(fileBuffer) : fileBuffer
              const fileItem: FileInterface = {
                id: `file-${Date.now()}-${Math.random()}`,
                name: part,
                path: `${rootPath}/${currentPath}`,
                kind: "file",
                content,
                isRemovable: true,
                isEditable: true,
              }

              currentLevel.push(fileItem)
              pathMap.set(currentPath, fileItem)
            }
            else {
              // It's a directory part
              let dirItem = pathMap.get(currentPath)
              if (!dirItem) {
                dirItem = {
                  id: `dir-${Date.now()}-${Math.random()}`,
                  name: part,
                  path: `${rootPath}/${currentPath}`,
                  kind: "directory",
                  children: [],
                  isRemovable: true,
                  isEditable: true,
                }
                currentLevel.push(dirItem)
                pathMap.set(currentPath, dirItem)
              }
              if (isDirectory(dirItem)) {
                currentLevel = dirItem.children
              }
            }
          }
        }

        resolve(fileData)
      })
    }).catch(reject)
  })
}

/**
 * Checks if a protocol package exists on server
 */
export async function checkProtocolPackageExists(packageId: string): Promise<boolean> {
  try {
    const packageInfoStr = localStorage.getItem(`protocol-package-${packageId}`)
    if (!packageInfoStr) {
      return false
    }

    const packageInfo: ProtocolPackage = JSON.parse(packageInfoStr)
    const response = await getAttachments(packageInfo.attachmentId)

    return !!response.data
  }
  catch {
    return false
  }
}

import type { ZipItem } from "@airalogy/shared/utils"
import type { UploadFileInfo } from "naive-ui"
import type { DirectoryInterface, FileInterface, FileSystemItem } from "../types"
import { DEFAULT_FILE_ID_MAP } from "@airalogy/shared/constants/protocol"
import { arrayBufferToString, canEditAsText, FILE_TYPES, getFileType, zipToPromise } from "@airalogy/shared/utils"
import { unzip, type Unzipped } from "fflate"
import { useMessage } from "naive-ui"
import { nanoid } from "nanoid"
import { ref } from "vue"
import { useUploadFileDataStore } from "../store/uploadFileDataStore"
import { isDirectory, isFile } from "../utils"
import { findByPath } from "../utils/file-tree"

const encoder = new TextEncoder()
// Files to be excluded from processing
const EXCLUDED_FILES = new Set([
  ".DS_Store",
  "Thumbs.db",
  ".git",
  "__MACOSX",
  ".gitignore",
  ".gitattributes",
  ".idea",
  ".vscode",
  "node_modules",
])

export const filenameIdMap = {
  "protocol.aimd": DEFAULT_FILE_ID_MAP.protocol,
  "model.py": DEFAULT_FILE_ID_MAP.model,
  "assigner.py": DEFAULT_FILE_ID_MAP.assigner,
  "version.py": DEFAULT_FILE_ID_MAP.version,
  "protocol.toml": DEFAULT_FILE_ID_MAP.toml_config,
}

export const fileMap = {
  [DEFAULT_FILE_ID_MAP.model]: "model.py",
  [DEFAULT_FILE_ID_MAP.protocol]: "protocol.aimd",
  [DEFAULT_FILE_ID_MAP.assigner]: "assigner.py",
  [DEFAULT_FILE_ID_MAP.version]: "version.py",
  [DEFAULT_FILE_ID_MAP.toml_config]: "protocol.toml",
}

export interface UploadedFileResult {
  id: string
  name: string
  path: string
  referencePath: string
  replaced: boolean
}

// Check if a file should be excluded based on its path
function shouldExcludeFile(path: string): boolean {
  // Check against excluded files/directories
  if (EXCLUDED_FILES.has(path))
    return true

  // Check if any part of the path is in excluded list
  const pathParts = path.split("/")
  return pathParts.some(part => EXCLUDED_FILES.has(part))
}

/**
 * Builds a map of directory levels to the directories at each level
 * Example:
 * {
 *   0: ['root'],
 *   1: ['root/src', 'root/docs'],
 *   2: ['root/src/components', 'root/docs/api']
 * }
 */
export function buildDirectoryLevelMap(pathList: string[]): Map<number, string[]> {
  const levelMap = new Map<number, string[]>()

  // Process each entry
  for (const path of pathList) {
    if (shouldExcludeFile(path))
      continue

    // Skip empty paths
    if (!path)
      continue

    // Split path into components and determine level
    const parts = path.split("/").filter(Boolean)

    // Process each directory level in the path
    for (let i = 0; i < parts.length; i++) {
      const level = i
      const dirPath = parts.slice(0, i + 1).join("/")

      // Skip if this is a file and we're at the last component
      if (i === parts.length - 1 && !path.endsWith("/"))
        continue

      // Add to the level map
      if (!levelMap.has(level)) {
        levelMap.set(level, [])
      }

      const levelDirs = levelMap.get(level)!
      if (!levelDirs.includes(dirPath)) {
        levelDirs.push(dirPath)
      }
    }
  }

  return levelMap
}

export function getRootPath(pathList: string[]): string {
  const levelMap = buildDirectoryLevelMap(pathList)
  return levelMap.get(0)?.[0] || ""
}

function createFileStructure(fileRecord: Unzipped): { fileStructure: DirectoryInterface[], rootPath: string } {
  const root: { [key: string]: DirectoryInterface } = {}
  const entries = Object.entries(fileRecord)

  // First pass: create all directories
  entries.forEach(([path]) => {
    if (shouldExcludeFile(path))
      return

    const parts = path.split("/").filter(Boolean)
    let currentPath = ""

    parts.forEach((part, index) => {
      const isLast = index === parts.length - 1
      const parentPath = currentPath
      currentPath = currentPath ? `${currentPath}/${part}` : part

      if (!isLast || path.endsWith("/")) {
        if (!root[currentPath]) {
          root[currentPath] = {
            id: nanoid(),
            name: part,
            path: currentPath,
            kind: "directory",
            children: [],
            status: "success",
            isRemovable: true,
            isEditable: true,
            isSelectable: true,
          }

          // Add to parent's children if it exists
          if (parentPath && root[parentPath] && root[parentPath].children) {
            root[parentPath].children!.push(root[currentPath])
          }
        }
      }
    })
  })

  const topLevelDir = getRootPath(entries.map(([path]) => path))

  // Second pass: add files
  entries.forEach(([path, content]) => {
    if (shouldExcludeFile(path) || path.endsWith("/"))
      return

    const parts = path.split("/").filter(Boolean)
    const fileName = parts.pop()!
    const parentPath = parts.join("/")

    let id: string

    if (topLevelDir && topLevelDir === parentPath) {
      id = filenameIdMap[fileName as keyof typeof filenameIdMap] || nanoid()
    }
    else {
      id = nanoid()
    }

    const isTextFile = FILE_TYPES.text.some(ext => fileName.toLowerCase().endsWith(ext))

    const fileObj: FileInterface = {
      id,
      name: fileName,
      path,
      kind: "file",
      content: isTextFile ? arrayBufferToString(content) : content,
      status: "success",
      isRemovable: true,
      isEditable: true,
      isSelectable: true,
    }

    if (parentPath && root[parentPath] && root[parentPath].children) {
      root[parentPath].children!.push(fileObj)
    }
  })

  // Return only top-level items
  return {
    fileStructure: Object.values(root).filter(item => !item.path.includes("/")) || [],
    rootPath: topLevelDir || "",
  }
}

function buildFilePath(parent: DirectoryInterface | null, rootPath: string, filename: string): string {
  const basePath = parent?.path || rootPath || ""
  return [basePath, filename].filter(Boolean).join("/")
}

function getReferencePath(path: string, rootPath: string): string {
  if (!path)
    return ""

  const normalizedRootPath = rootPath.replace(/^\/+|\/+$/g, "")
  const normalizedPath = path.replace(/^\/+/, "")

  if (!normalizedRootPath)
    return normalizedPath

  const rootPrefix = `${normalizedRootPath}/`
  if (normalizedPath === normalizedRootPath)
    return ""

  if (normalizedPath.startsWith(rootPrefix))
    return normalizedPath.slice(rootPrefix.length)

  return normalizedPath
}

function revokeBlobUrl(fileUrl?: string) {
  if (fileUrl?.startsWith("blob:")) {
    URL.revokeObjectURL(fileUrl)
  }
}

async function readUploadedFile(file: File): Promise<Pick<FileInterface, "content" | "fileSize" | "fileType" | "fileUrl">> {
  if (canEditAsText(file.name)) {
    return {
      content: await file.text(),
      fileSize: file.size,
      fileType: getFileType(file.name),
      fileUrl: undefined,
    }
  }

  const arrayBuffer = await file.arrayBuffer()

  return {
    content: new Uint8Array(arrayBuffer),
    fileSize: file.size,
    fileType: getFileType(file.name),
    fileUrl: URL.createObjectURL(file),
  }
}

export function useFileUpload() {
  const message = useMessage()
  const isUploading = ref(false)
  const uploadFileDataStore = useUploadFileDataStore()
  const { setFileData, addFileOrFolder, updateFileItem } = uploadFileDataStore

  async function upsertLocalFile(file: File, parent: DirectoryInterface | null = null): Promise<UploadedFileResult> {
    const targetPath = buildFilePath(parent, uploadFileDataStore.rootPath, file.name)
    const filePayload = await readUploadedFile(file)
    const existingItem = uploadFileDataStore.fileData ? findByPath(uploadFileDataStore.fileData, targetPath) : null

    if (existingItem && !isFile(existingItem)) {
      throw new Error(`Cannot upload file to directory path "${targetPath}"`)
    }

    if (existingItem && isFile(existingItem)) {
      revokeBlobUrl(existingItem.fileUrl)

      await updateFileItem(existingItem.id, {
        content: filePayload.content,
        fileSize: filePayload.fileSize,
        fileType: filePayload.fileType,
        fileUrl: filePayload.fileUrl,
      })

      return {
        id: existingItem.id,
        name: file.name,
        path: targetPath,
        referencePath: getReferencePath(targetPath, uploadFileDataStore.rootPath),
        replaced: true,
      }
    }

    const fileId = nanoid()

    addFileOrFolder({
      kind: "file",
      name: file.name,
      status: "success",
      id: fileId,
      content: "",
      path: targetPath,
      parent,
    })

    await updateFileItem(fileId, {
      content: filePayload.content,
      fileSize: filePayload.fileSize,
      fileType: filePayload.fileType,
      fileUrl: filePayload.fileUrl,
    })

    return {
      id: fileId,
      name: file.name,
      path: targetPath,
      referencePath: getReferencePath(targetPath, uploadFileDataStore.rootPath),
      replaced: false,
    }
  }

  async function uploadLocalFiles(files: File[], parent: DirectoryInterface | null = null): Promise<UploadedFileResult[]> {
    const validFiles = files.filter((file) => {
      if (shouldExcludeFile(file.name)) {
        message.warning(`File "${file.name}" was skipped because it is reserved or generated by the system`)
        return false
      }

      return true
    })

    if (validFiles.length === 0) {
      return []
    }

    isUploading.value = true

    try {
      const results: UploadedFileResult[] = []

      for (const file of validFiles) {
        results.push(await upsertLocalFile(file, parent))
      }

      if (results.length === 1) {
        const [result] = results
        const actionLabel = result.replaced ? "Updated" : "Uploaded"
        const referenceHint = result.referencePath ? ` Reference path: ${result.referencePath}` : ""
        message.success(`${actionLabel} "${result.name}".${referenceHint}`)
      }
      else {
        message.success(`Uploaded ${results.length} files`)
      }

      return results
    }
    catch (error) {
      console.error("Upload error:", error)
      message.error("Failed to process file upload")
      return []
    }
    finally {
      isUploading.value = false
    }
  }

  async function processZipFile(file: File): Promise<void> {
    const arrayBuffer = await file.arrayBuffer()
    const uint8Array = new Uint8Array(arrayBuffer)

    return new Promise((resolve, reject) => {
      unzip(uint8Array, (err, unzipped) => {
        if (err) {
          reject(new Error("Failed to unzip file"))
          return
        }

        try {
          const { fileStructure, rootPath } = createFileStructure(unzipped)
          // TODO: just set root's first child as fileData
          if (fileStructure.length === 1 && fileStructure[0]?.kind === "directory") {
            if (fileStructure[0]?.children) {
              setFileData(fileStructure[0]?.children)
            }
          }
          else {
            setFileData(fileStructure)
          }

          uploadFileDataStore.rootPath = rootPath
          resolve()
        }
        catch (error) {
          reject(error)
        }
      })
    })
  }

  async function handleUpload(info: UploadFileInfo) {
    const file = info.file
    if (!file) {
      message.error("No file provided")
      return
    }

    try {
      if (file.type === "application/zip" || file.name.endsWith(".zip")) {
        isUploading.value = true
        await processZipFile(file)
        message.success("ZIP file processed successfully")
      }
      else {
        await uploadLocalFiles([file])
      }
    }
    catch (error) {
      console.error("Upload error:", error)
      message.error("Failed to process file")
    }
    finally {
      isUploading.value = false
    }
  }

  async function compressFiles(zip = true, outputItems = false) {
    const { fileData, rootPath } = uploadFileDataStore

    if (!fileData || fileData.length === 0) {
      message.error("No files to compress")
      return
    }

    try {
      // Prepare data structure for zip
      const zipData: Record<string, Uint8Array> = {}

      // Determine the top-level directory name
      const topDirName = rootPath || "files"
      const root = topDirName.endsWith("/") ? topDirName : `${topDirName}/`

      // console.log("[compressFiles] Using top directory name:", topDirName)
      // console.log("[compressFiles] fileData structure:", JSON.stringify(fileData.map(item => ({
      //   filename: item.name,
      //   kind: item.kind,
      //   hasChildren: isDirectory(item) && item.children ? item.children.length > 0 : false,
      // })), null, 2))

      // Explicitly add the top-level directory entry to ensure it exists
      zipData[root] = new Uint8Array(0)

      // Process the file structure
      flattenStructure({ items: fileData, basePath: "", topDirName, zipData })

      // Check if we have files to compress
      if (Object.keys(zipData).length === 0) {
        message.warning("No valid files to compress")
        return
      }

      // console.log("[compressFiles] Final zip structure keys:", Object.keys(zipData))

      // Compress the files
      const items: ZipItem[] = outputItems ? convertFilesToZipItems(fileData, zipData, topDirName) : []
      const zipped = zip ? await zipToPromise(zipData, { level: 6 }) : new Uint8Array(0)

      return { items, file: zipped, root }
    }
    catch (error) {
      console.error("Compression error:", error)
      message.error("Failed to compress files")
      return null
    }
  }

  return {
    isUploading,
    processZipFile,
    handleUpload,
    uploadLocalFiles,
    compressFiles,
  }
}

// Recursive function to flatten file structure
function flattenStructure(payload: { items: FileSystemItem[], basePath: string, topDirName: string, zipData: Record<string, Uint8Array> }) {
  const { items, basePath, topDirName, zipData } = payload

  for (const item of items) {
    // Create path ensuring everything is inside the top directory
    let itemPath = item.name

    // If we already have a base path, append to it
    if (basePath) {
      itemPath = `${basePath}/${itemPath}`
    }
    // Otherwise, put it inside the top directory
    else {
      itemPath = `${topDirName}/${itemPath}`
    }

    // Skip excluded files
    if (shouldExcludeFile(itemPath))
      continue

    if (isFile(item)) {
      if (item.content) {
        // Handle file content based on type
        let content: Uint8Array

        // Check if the content is already a Uint8Array (binary data)
        if (ArrayBuffer.isView(item.content) && item.content.constructor === Uint8Array) {
          content = item.content as Uint8Array
        }
        // Check if it's a string (text data)
        else if (typeof item.content === "string") {
          content = encoder.encode(item.content)
        }
        // Default case - leave it
        else {
          content = item.content
        }

        // Add file to zip data
        zipData[itemPath] = content
      }
      else {
        console.warn(`File ${itemPath} has no content, skipping`)
      }
    }
    else if (item.kind === "directory" && item.children) {
      // Add directory entry with trailing slash to ensure empty directories are preserved
      zipData[`${itemPath}/`] = new Uint8Array(0)

      // Process children
      flattenStructure({ items: item.children, basePath: itemPath, topDirName, zipData })
    }
    else if (item.kind === "directory") {
      // Handle empty directory case
      zipData[`${itemPath}/`] = new Uint8Array(0)
    }
  }
}

export function convertFilesToZipItems(data: FileSystemItem[], zipData: Record<string, Uint8Array<ArrayBufferLike>>, root: string): ZipItem[] {
  const items: ZipItem[] = [{
    isDirectory: true,
    compression: 0,
    name: root,
    originalSize: 0,
    path: `${root}/`,
    size: 0,
    content: new Uint8Array(0),
    lastModified: new Date(),
  }]

  data.forEach((item) => {
    const { name, path, fileSize } = item
    const isDir = isDirectory(item)
    if (isDir) {
      items.push(...convertFilesToZipItems(item.children, zipData, path))
    }
    else {
      items.push({
        isDirectory: false,
        compression: 0,
        name,
        path,
        originalSize: fileSize || 0,
        content: zipData[path],
        size: fileSize || 0,
      })
    }
  })

  return items
}

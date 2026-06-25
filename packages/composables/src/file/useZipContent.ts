import type { UploadFileInfo } from "naive-ui"
import { arrayBufferToString, ENV_EXTENSIONS, type UnzipFileInfo, unzipToPromise, type ZipItem } from "@airalogy/shared/utils"
import { computed, ref } from "vue"
import { useBoolean } from "../useBoolean"
import { useClosableMessage } from "../useClosableMessage"

interface FileChangeData {
  file: UploadFileInfo
  fileList: UploadFileInfo[]
}

export function useZipContent() {
  const { bool: isLoading, setTrue: startLoading, setFalse: stopLoading } = useBoolean()
  const zipContent = ref<{ items: ZipItem[], root: string }>({ items: [], root: "" })
  const currentPath = ref<string[]>([])
  const selectedFile = ref<ZipItem | null>(null)
  const fileContent = ref<Record<string, string>>({})
  const message = useClosableMessage()

  // Add state for .env file detection
  const envFiles = ref<Record<string, string>>({})
  // const envFileContent = ref<string>("")
  // const envExampleContent = ref<string>("")

  // Get current directory content based on path
  const currentDirContent = computed(() => {
    const currentFullPath = currentPath.value.join("/")
    return zipContent.value.items
      .filter((item) => {
        // Remove trailing slash for directories
        const itemPath = item.path.replace(/\/$/, "")
        const itemParentPath = itemPath.split("/").slice(0, -1).join("/")

        // At root level, show items that are directly under root
        if (!currentFullPath) {
          return itemParentPath === ""
        }

        // For other levels, show items whose parent path matches current path
        return itemParentPath === currentFullPath
      })
      .sort((a, b) => {
        // Directories first, then files
        if (a.isDirectory !== b.isDirectory) {
          return a.isDirectory ? -1 : 1
        }
        return a.name.localeCompare(b.name)
      })
  })

  // Handle file upload
  async function handleFileChange(data: FileChangeData) {
    if (!data.file.file)
      return

    try {
      startLoading()
      const buffer = await data.file.file.arrayBuffer()
      const uint8Array = new Uint8Array(buffer)

      let root = ""
      const fileMetadata = new Map<string, UnzipFileInfo>()
      const unzipped = await unzipToPromise(uint8Array, {
        filter(file) {
          const { name } = file
          const isMACOSX = name.startsWith("__MACOSX") || name.endsWith(".DS_Store")
          if (isMACOSX)
            return false

          if (!root && /[^/]+\/$/.test(file.name)) {
            root = file.name
            return false
          }

          // Store metadata for each file
          fileMetadata.set(name, file)

          return true
        },
      })

      const items: ZipItem[] = []
      for (const [path, content] of Object.entries(unzipped)) {
        if (path.endsWith("/"))
          continue

        const metadata = fileMetadata.get(path)
        const name = path.split("/").pop() || path

        if (metadata) {
          if (path.startsWith(root) && ENV_EXTENSIONS.includes(name)) {
            envFiles.value[path] = arrayBufferToString(content)
          }

          items.push({
            ...metadata,
            name,
            path,
            isDirectory: false,
            content,
          })
        }
        else {
          items.push({
            name,
            path,
            isDirectory: false,
            size: content.length,
            originalSize: content.length,
            compression: 0,
          })
        }
      }

      // Add directory entries
      const directories = new Set<string>()
      items.forEach((item) => {
        const parts = item.path.split("/")
        parts.pop() // Remove filename
        let currentPath = ""
        parts.forEach((part) => {
          currentPath += `${part}/`
          if (!directories.has(currentPath)) {
            directories.add(currentPath)
            items.push({
              name: part,
              path: currentPath,
              isDirectory: true,
              size: 0,
              originalSize: 0,
              compression: 0,
            })
          }
        })
      })

      zipContent.value = { items, root }
    }
    catch (error) {
      message.error(`Error processing ZIP file: ${(error as Error).message}`)
    }
    finally {
      stopLoading()
    }
  }

  // Navigation
  function navigateTo(index: number) {
    currentPath.value = currentPath.value.slice(0, index + 1)
    selectedFile.value = null
  }

  // Handle item click
  async function handleItemClick(item: ZipItem) {
    if (item.isDirectory) {
      currentPath.value.push(item.name)
      return
    }

    selectedFile.value = item
    if (fileContent.value[item.path]) {
      return
    }
    if (item.content) {
      startLoading()
      try {
        fileContent.value[item.path] = arrayBufferToString(item.content)
      }
      catch (error) {
        console.error("Error reading file:", error)
      }
      finally {
        stopLoading()
      }
    }
  }

  // Reset preview
  function resetPreview() {
    zipContent.value = { items: [], root: "" }
    currentPath.value = []
    selectedFile.value = null
    envFiles.value = {}
  }

  return {
    isLoading,
    zipContent,
    currentPath,
    selectedFile,
    fileContent,
    currentDirContent,
    handleFileChange,
    navigateTo,
    handleItemClick,
    resetPreview,
    // Add new exports for .env detection
    // envFileContent,
    // envExampleContent,
    envFiles,
  }
}

import type { Ref } from "vue"
import type { DirectoryInterface, DirectorySuperInterface, FileInterface, FileSystemItem } from "../types"
import type { DirEnt, FileSystemAPI } from "../types/fileSystem"
import { arrayBufferToString, createLocalforage } from "@airalogy/shared/utils"
import { nanoid } from "nanoid"
// Import storage monitoring utilities
import { DEFAULT_FILE_ID_MAP, logStorageDetails } from "@airalogy/shared"
import { useOPFS } from "../composables/useOPFS"

// interface PrettierConfigResult {
//   value: string | null
//   name: string
// }

// type ConfigParser = (str: string) => Record<string, any>

// const basePrettierConfig = {
//   tabWidth: 4,
//   useTabs: false,
//   semi: true,
//   singleQuote: false,
//   printWidth: 100,
//   trailingComma: "es5" as const,
//   arrowParens: "always" as const,
// }

// // 常见的prettier文件类型
// const prettierType: string[] = [
//   "prettier",
//   ".prettierrc",
//   ".prettierrc.json",
//   ".prettierrc.yml",
//   ".prettierrc.yaml",
//   ".prettierrc.json5",
//   ".prettierrc.js",
//   "prettier.config.js",
//   ".prettierrc.mjs",
//   "prettier.config.mjs",
//   ".prettierrc.cjs",
//   "prettier.config.cjs",
//   ".prettierrc.toml",
// ]

// // 处理JSON
// function convertJSONToObject(str: string) {
//   // 使用正则表达式提取 {} 中的内容
//   const match = str.match(/\{([\s\S]*)\}/)

//   if (match) {
//     str = `{${match[1]}}`
//   }
//   else {
//     console.error("未找到有效的对象内容")

//     return null
//   }

//   // 移除 // 后面的注释
//   str = str.replace(/\/\/.*$/gm, "")
//   // 将所有的单引号替换为双引号
//   str = str.replace(/'/g, "\"")

//   // 将没有引号的属性名加上双引号
//   str = str.replace(/(\w+):/g, "\"$1\":")

//   // 移除末尾的分号（如果有的话）
//   str = str.replace(/;$/, "")

//   // 使用 Function 构造函数解析字符串
//   try {
//     // eslint-disable-next-line no-new-func
//     const obj = new Function(`return ${str};`)()

//     return obj
//   }
//   catch (error) {
//     console.error("解析失败:", error)

//     return null
//   }
// }
// // 处理JS
// function convertJSToObject(str: string) {
//   // 使用正则表达式提取 = {} 中的内容
//   const match = str.match(/=\s*(\{[\s\S]*\})/)

//   if (match) {
//     str = match[1]
//   }
//   else {
//     console.error("未找到有效的对象内容")

//     return null
//   }

//   // 移除 // 后面的注释
//   str = str.replace(/\/\/.*$/gm, "")

//   // 将所有的单引号替换为双引号
//   str = str.replace(/'/g, "\"")

//   // 将没有引号的属性名加上双引号
//   str = str.replace(/(\w+):/g, "\"$1\":")

//   // 移除末尾的分号（如果有的话）
//   str = str.replace(/;$/, "")

//   // 使用 Function 构造函数解析字符串
//   try {
//     // eslint-disable-next-line no-new-func
//     const obj = new Function(`return ${str};`)()

//     return obj
//   }
//   catch (error) {
//     console.error("解析失败:", error)

//     return null
//   }
// }
// // 处理YAML
// function convertYAMLToObject(str: string) {
//   // 移除注释和空行
//   const lines = str.split("\n").filter((line) => {
//     line = line.trim()

//     return line && !line.startsWith("#")
//   })

//   const result: { [key: string]: any } = {}

//   for (const line of lines) {
//     // 分割键值对
//     const [key, value] = line.split(":").map(part => part.trim())

//     if (key && value) {
//       // 处理布尔值
//       if (value.toLowerCase() === "true") {
//         result[key] = true
//       }
//       else if (value.toLowerCase() === "false") {
//         result[key] = false
//       }
//       // 处理数字
//       else if (!Number.isNaN(Number(value))) {
//         result[key] = Number(value)
//       }
//       // 处理字符串（移除引号）
//       else {
//         result[key] = value.replace(/^["']|["']$/g, "")
//       }
//     }
//   }

//   return result
// }
// // 处理TOML
// function convertTOMLToObject(str: string) {
//   // 移除注释和空行
//   const lines = str.split("\n").filter((line) => {
//     line = line.trim()

//     return line && !line.startsWith("#")
//   })

//   const result: { [key: string]: any } = {}

//   for (const line of lines) {
//     // 分割键值对
//     const [key, value] = line.split("=").map(part => part.trim())

//     if (key && value) {
//       // 处理布尔值
//       if (value.toLowerCase() === "true") {
//         result[key] = true
//       }
//       else if (value.toLowerCase() === "false") {
//         result[key] = false
//       }
//       // 处理数字
//       else if (!Number.isNaN(Number(value))) {
//         result[key] = Number(value)
//       }
//       // 处理字符串（移除引号）
//       else {
//         result[key] = value.replace(/^["']|["']$/g, "")
//       }
//     }
//   }

//   return result
// }

// const prettierMap: Record<string, ConfigParser[]> = {
//   prettier: [convertJSONToObject, convertYAMLToObject],
//   _prettierrc: [convertJSONToObject, convertYAMLToObject],
//   _prettierrc_json: [convertJSONToObject],
//   _prettierrc_yml: [convertYAMLToObject],
//   _prettierrc_yaml: [convertYAMLToObject],
//   _prettierrc_json5: [convertJSONToObject],
//   _prettierrc_mjs: [convertJSToObject],
//   prettier_config_mjs: [convertJSToObject],
//   _prettierrc_cjs: [convertJSToObject],
//   prettier_config_cjs: [convertJSToObject],
//   _prettierrc_toml: [convertTOMLToObject],
// }

// export function getPrettierConfig(file: FileSystemItem[] | null): Record<string, any> {
//   if (!file)
//     return basePrettierConfig

//   const fileData = findPrettierConfig(isDirectory(file[0]) ? file[0].children : [])
//   if (!fileData.value)
//     return basePrettierConfig

//   let config: Record<string, any> = {}

//   prettierMap[fileData.name].some((parser) => {
//     config = parser(fileData.value as string)

//     return config && Object.keys(config).length > 0
//   })

//   return config
// }

// // 获取.prettierrc.js文件的内容
// function findPrettierConfig(list: any[]): PrettierConfigResult {
//   const findItem = list.find(item => prettierType.includes(item.filename))

//   return { value: findItem ? findItem.value : null, name: findItem.filename.split(".").join("_") }
// }

export function isDirectory(
  directory: any,
): directory is DirectoryInterface | DirectorySuperInterface {
  return directory?.kind === "directory"
}

export function isFile(file: any): file is FileInterface {
  return file?.kind === "file"
}
export const DEFAULT_FILE_DATA: FileInterface[] = [
  {
    id: DEFAULT_FILE_ID_MAP.protocol,
    name: "protocol.aimd",
    path: "protocol/protocol.aimd",
    kind: "file",
    status: "success",
    isRemovable: false,
    isEditable: false,
    content: `# AIMD Template

## Basic Information

Experimenter Name: {{var|experimenter_name: UserName}}
Experiment Time: {{var|experiment_time: CurrentTime}}

## Experimental Steps

{{step|step_name}} Step Description`,
  },
  // {
  //   id: "airalogy_version",
  //   filename: "version.py",
  //   path: "protocol/version.py",
  //   kind: "file",
  //   status: "success",
  //   isRemovable: false,
  //   isEditable: false,
  //   value: "VERSION = \"0.0.1\"",
  // },
  {
    id: DEFAULT_FILE_ID_MAP.toml_config,
    name: "protocol.toml",
    path: "protocol/protocol.toml",
    kind: "file",
    status: "success",
    isRemovable: false,
    isEditable: false,
    content: `[airalogy_protocol]
id = "my_protocol"
version = "0.0.1"
name = "My Protocol"
authors = [
    {name = "User", email = "user@example.com", airalogy_user_id = "airalogy.id.user.default"}
]
maintainers = [
    {name = "User", email = "user@example.com", airalogy_user_id = "airalogy.id.user.default"}
]
disciplines = ["biology"]
keywords = ["protocol"]
license = "CC-BY-4.0"
`,
  },
]

// Initialize localforage instance with localStorage driver
export const fsStore = createLocalforage<Record<string, any>>("local", "protocol-editor")
// Get or create the project data
export async function getProjectDataFromLocal(projectId: string, downloadProtocolPackage: (packageId: string) => Promise<(FileSystemItem)[] | null>): Promise<(FileSystemItem)[] | null> {
  const { loadProject } = useOPFS()

  // Try loading from OPFS first
  const opfsData = await loadProject(projectId)
  if (opfsData) {
    console.log(`[getProjectDataFromLocal] Successfully loaded ${projectId} from OPFS`)
    return opfsData
  }

  // Fallback to localforage (for server references and older data)
  const data = await fsStore.getItem(projectId)
  if (data) {
    const parsedData = JSON.parse(data as string)

    // Check if this is a server reference
    if (parsedData._type === "server_reference") {
      try {
        console.log(`[getProjectDataFromLocal] Loading ${projectId} from server`)

        const serverData = await downloadProtocolPackage(parsedData.packageId)
        if (serverData) {
          console.log(`[getProjectDataFromLocal] Successfully loaded ${projectId} from server`)
          // Save to OPFS for future loads
          await saveProjectData(projectId, serverData, async () => {})
          return serverData
        }
        else {
          console.warn(`[getProjectDataFromLocal] Failed to load ${projectId} from server, reference data:`, parsedData)
          return null
        }
      }
      catch (error) {
        console.error(`[getProjectDataFromLocal] Error loading ${projectId} from server:`, error)
        return null
      }
    }

    // Regular localStorage data (migrate to OPFS)
    console.log(`[getProjectDataFromLocal] Migrating ${projectId} from localStorage to OPFS`)
    await saveProjectData(projectId, parsedData, async () => {})
    return parsedData
  }

  return null
}

// Save the project data
export async function saveProjectData(projectId: string, data: (FileSystemItem)[], uploadProtocolPackage: (packageId: string, files: (FileSystemItem)[], rootPath: string) => Promise<void>): Promise<void> {
  const { saveProject } = useOPFS()
  try {
    console.log(`[saveProjectData] Saving ${projectId} to OPFS`)
    await saveProject(projectId, data)
    console.log(`[saveProjectData] Successfully stored ${projectId} in OPFS`)

    // Clean up old localStorage data if it exists
    await fsStore.removeItem(projectId)
  }
  catch (error) {
    console.error("[saveProjectData] Failed to save project data to OPFS:", error)
    await logStorageDetails("saveProjectData OPFS Error")
    throw new Error("Failed to save project data to OPFS. Please check browser permissions or contact support.")
  }
}

export function countTotalFiles(items: (FileSystemItem)[]): number {
  let count = 0
  for (const item of items) {
    if (isFile(item)) {
      count++
    }
    else if (item.children) {
      count += countTotalFiles(item.children)
    }
  }
  return count
}

export async function renameProjectData(targetId: string, newId: string, downloadProtocolPackage: (packageId: string) => Promise<(FileSystemItem)[] | null>): Promise<void> {
  const { saveProject, deleteProject } = useOPFS()
  const data = await getProjectDataFromLocal(targetId, downloadProtocolPackage)
  if (data) {
    await saveProject(newId, data)
    await deleteProject(targetId)
    // Also remove from localforage in case it was a fallback
    await fsStore.removeItem(targetId)
  }
}

// Mock FileSystem implementation
export class MockFileSystem implements FileSystemAPI {
  private projectId: string
  private projectData: (FileSystemItem)[] | null
  private rootPath: string
  private saveProjectData: (id: string, data: (FileSystemItem)[]) => Promise<void>

  constructor(projectId: string, projectData: Ref<(FileSystemItem)[] | null>, rootPath: string, saveProjectData: (id: string, data: (FileSystemItem)[]) => Promise<void>) {
    this.projectId = projectId
    this.projectData = projectData as any
    this.rootPath = rootPath
    this.saveProjectData = saveProjectData
  }

  // Save the project data
  private async saveData(): Promise<void> {
    if (this.projectData) {
      await this.saveProjectData(this.projectId, this.projectData)
    }
  }

  async readdir(path: string, options: "buffer" | { encoding: "buffer", withFileTypes?: false }): Promise<Uint8Array[]>
  async readdir(path: string, options?: { encoding?: BufferEncoding | null, withFileTypes?: false } | BufferEncoding | null): Promise<string[]>
  async readdir(path: string, options: { encoding: "buffer", withFileTypes: true }): Promise<DirEnt<Uint8Array>[]>
  async readdir(path: string, options: { encoding?: BufferEncoding | null, withFileTypes: true }): Promise<DirEnt<string>[]>
  async readdir(
    path: string,
    options?: any,
  ): Promise<string[] | Uint8Array[] | DirEnt<string>[] | DirEnt<Uint8Array>[]> {
    if (!this.projectData) {
      return []
    }
    const encoder = new TextEncoder()

    // Normalize path
    const normalizedPath = path === "/" ? "" : path.startsWith("/") ? path.slice(1) : path

    // Find the directory
    const dir = this.findDirectoryByPath(normalizedPath, this.projectData)
    if (!dir) {
      throw new Error(`Directory not found: ${path}`)
    }

    // Get the children
    const children = dir.children || []

    // Handle different return types based on options
    const withFileTypes = options?.withFileTypes === true
    const encoding = options?.encoding === "buffer" || options === "buffer" ? "buffer" : "utf8"

    if (withFileTypes) {
      // Return DirEnt objects
      return children.map((child) => {
        const name = encoding === "buffer"
          ? encoder.encode(child.name)
          : child.name

        return {
          name,
          isDirectory: () => child.kind === "directory",
          isFile: () => child.kind === "file",
          isSymbolicLink: () => false,
          isSocket: () => false,
          isBlockDevice: () => false,
          isCharacterDevice: () => false,
          isFIFO: () => false,
        } as any
      })
    }
    else {
      // Return names
      const names = children.map(child => child.name)
      if (encoding === "buffer") {
        return names.map(name => encoder.encode(name))
      }
      return names
    }
  }

  // Helper method to find a directory by path
  findDirectoryByPath(path: string, directories: (FileSystemItem)[]): DirectoryInterface | null {
    if (!path || path === "/" || path === "") {
      // Create a virtual root directory that contains all top-level directories
      return {
        id: "root",
        name: "",
        path: "",
        kind: "directory",
        children: [{
          id: "topDir",
          name: this.rootPath,
          path: this.rootPath,
          kind: "directory",
          children: directories,
        }],
      }
    }

    const parts = path.split("/").filter(Boolean)
    let current: DirectoryInterface | null = this.findDirectoryByPath("", directories)

    for (const part of parts) {
      if (!current || !current.children) {
        return null
      }

      const found = current.children.find(
        child => child.name === part && child.kind === "directory",
      ) as DirectoryInterface

      if (!found) {
        return null
      }

      current = found
    }

    return current
  }

  // Helper method to find a file by path
  findFileByPath(path: string, directories: (FileSystemItem)[]): FileInterface | null {
    const parts = path.split("/").filter(Boolean)
    const filename = parts.pop()

    if (!filename) {
      return null
    }

    const dirPath = parts.join("/")
    const dir = this.findDirectoryByPath(dirPath, directories)

    if (!dir || !dir.children) {
      return null
    }

    return dir.children.find(
      (child): child is FileInterface => child.name === filename && child.kind === "file",
    ) || null
  }

  async readFile(path: string, encoding?: null): Promise<Uint8Array>
  async readFile(path: string, encoding: BufferEncoding): Promise<string>
  async readFile(path: string, encoding?: BufferEncoding | null): Promise<string | Uint8Array> {
    if (!this.projectData) {
      throw new Error("Project data not available")
    }

    // Normalize path
    const normalizedPath = path.startsWith("/") ? path.slice(1) : path

    // Find the file
    const file = this.findFileByPath(normalizedPath, this.projectData)
    if (!file) {
      throw new Error(`File not found: ${path}`)
    }

    // Get file content
    const content = file.content || ""

    // Return content based on encoding
    if (encoding === null && typeof content === "string") {
      return new TextEncoder().encode(content)
    }
    return content
  }

  async writeFile(path: string, data: string | Uint8Array, options?: string | { encoding?: string | null } | null): Promise<void> {
    if (!this.projectData) {
      throw new Error("Project data not available")
    }

    // Normalize path
    const normalizedPath = path.startsWith("/") ? path.slice(1) : path

    // Convert Uint8Array to string if needed
    const content = data instanceof Uint8Array ? arrayBufferToString(data) : data

    // Get the directory path and filename
    const parts = normalizedPath.split("/").filter(Boolean)
    const filename = parts.pop()

    if (!filename) {
      throw new Error("Invalid file path")
    }

    const dirPath = parts.join("/")

    // Find the parent directory
    let dir = this.findDirectoryByPath(dirPath, this.projectData)

    // Create parent directories if they don't exist
    if (!dir) {
      await this.mkdir(dirPath.length > 0 ? `/${dirPath}` : "/", { recursive: true })
      dir = this.findDirectoryByPath(dirPath, this.projectData)

      if (!dir) {
        throw new Error(`Failed to create directory: ${dirPath}`)
      }
    }

    // Check if file already exists
    const existingFile = dir.children
      ? this.findFileByPath(normalizedPath, dir.children)
      : null

    if (existingFile) {
      // Update existing file
      existingFile.content = content
    }
    else if (dir.children) {
      // Create new file
      const newFile: FileInterface = {
        id: nanoid(),
        name: filename,
        path: normalizedPath,
        kind: "file",
        content,
        status: "success",
        isRemovable: true,
        isEditable: true,
      }
      dir.children.push(newFile)
    }

    // Save changes
    await this.saveData()
  }

  async mkdir(path: string, options?: { recursive?: false }): Promise<void>
  async mkdir(path: string, options: { recursive: true }): Promise<string>
  async mkdir(path: string, options?: { recursive?: boolean }): Promise<void | string> {
    if (!this.projectData) {
      throw new Error("Project data not available")
    }

    // Normalize path
    const normalizedPath = path === "/" ? "" : path.startsWith("/") ? path.slice(1) : path

    // If directory already exists, return early
    const existingDir = this.findDirectoryByPath(normalizedPath, this.projectData)
    if (existingDir) {
      return options?.recursive ? normalizedPath : undefined
    }

    const parts = normalizedPath.split("/").filter(Boolean)
    let currentPath = ""
    let currentDir: DirectoryInterface | null = this.findDirectoryByPath("", this.projectData)

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      const isLast = i === parts.length - 1

      currentPath = currentPath ? `${currentPath}/${part}` : part

      if (!currentDir) {
        // This case should not be reached if the traversal logic is correct.
        // It indicates a deeper problem if the parent directory reference is lost.
        throw new Error(`Parent directory not found: ${currentPath}`)
      }

      // Ensure children array exists to prevent errors on malformed directory data
      if (!currentDir.children) {
        currentDir.children = []
      }

      let nextDir = currentDir.children.find(
        child => child.name === part && child.kind === "directory",
      ) as DirectoryInterface | undefined

      if (!nextDir) {
        // If a directory in the path doesn't exist, create it.
        // This makes the creation behavior of mkdir effectively recursive.
        nextDir = {
          id: nanoid(),
          name: part,
          path: currentPath,
          kind: "directory",
          children: [],
          status: "success",
          isRemovable: true,
          isEditable: true,
        }
        currentDir.children.push(nextDir)
      }

      currentDir = nextDir
    }

    // Save changes
    await this.saveData()

    // Return the created directory path for recursive option
    if (options?.recursive) {
      return normalizedPath
    }
  }

  async rm(path: string, options?: { force?: boolean, recursive?: boolean }): Promise<void> {
    if (!this.projectData) {
      throw new Error("Project data not available")
    }

    // Normalize path
    const normalizedPath = path.startsWith("/") ? path.slice(1) : path

    // Split path into parts
    const parts = normalizedPath.split("/").filter(Boolean)
    const filename = parts.pop()

    if (!filename) {
      throw new Error("Invalid path")
    }

    const dirPath = parts.join("/")
    const parentDir = this.findDirectoryByPath(dirPath, this.projectData)

    if (!parentDir || !parentDir.children) {
      if (options?.force) {
        return
      }
      throw new Error(`Parent directory not found: ${dirPath}`)
    }

    const itemIndex = parentDir.children.findIndex(child => child.name === filename)

    if (itemIndex === -1) {
      if (options?.force) {
        return
      }
      throw new Error(`Item not found: ${path}`)
    }

    const item = parentDir.children[itemIndex]

    // Check if trying to remove a non-empty directory without recursive option
    if (isDirectory(item) && item.children && item.children.length > 0 && !options?.recursive) {
      throw new Error(`Directory not empty: ${path}`)
    }

    // Remove the item
    parentDir.children.splice(itemIndex, 1)

    // Save changes
    await this.saveData()
  }

  async rename(oldPath: string, newPath: string): Promise<void> {
    if (!this.projectData) {
      throw new Error("Project data not available")
    }

    // Normalize paths
    const normalizedOldPath = oldPath.startsWith("/") ? oldPath.slice(1) : oldPath
    const normalizedNewPath = newPath.startsWith("/") ? newPath.slice(1) : newPath

    // Find the item to rename
    const oldParts = normalizedOldPath.split("/").filter(Boolean)
    const oldFilename = oldParts.pop()

    if (!oldFilename) {
      throw new Error("Invalid source path")
    }

    const oldDirPath = oldParts.length > 0 ? oldParts.join("/") : this.rootPath
    const oldParentDir = this.findDirectoryByPath(oldDirPath, this.projectData)

    if (!oldParentDir || !oldParentDir.children) {
      throw new Error(`Source parent directory not found: ${oldDirPath}`)
    }

    const itemIndex = oldParentDir.children.findIndex(child => child.name === oldFilename)

    if (itemIndex === -1) {
      throw new Error(`Source item not found: ${oldPath}`)
    }

    const item = oldParentDir.children[itemIndex]

    // Parse new path
    const newParts = normalizedNewPath.split("/").filter(Boolean)
    const newFilename = newParts.pop()

    if (!newFilename) {
      throw new Error("Invalid destination path")
    }

    const newDirPath = newParts.length > 0 ? newParts.join("/") : this.rootPath

    // Find or create the destination directory
    let newParentDir = this.findDirectoryByPath(newDirPath, this.projectData)

    if (!newParentDir) {
      // Create the destination directory if it doesn't exist
      await this.mkdir(newDirPath.length > 0 ? `/${newDirPath}` : "/", { recursive: true })
      newParentDir = this.findDirectoryByPath(newDirPath, this.projectData)

      if (!newParentDir) {
        throw new Error(`Failed to create destination directory: ${newDirPath}`)
      }
    }

    // Check if destination already exists
    if (newParentDir.children && newParentDir.children.some(child => child.name === newFilename)) {
      throw new Error(`Destination already exists: ${newPath}`)
    }

    // Update the item
    const updatedItem = {
      ...item,
      filename: newFilename,
      path: normalizedNewPath,
    }

    // Remove from old location
    oldParentDir.children.splice(itemIndex, 1)

    // Add to new location
    if (newParentDir.children) {
      newParentDir.children.push(updatedItem)
    }
    else {
      newParentDir.children = [updatedItem]
    }

    // Save changes
    await this.saveData()
  }

  // watch(filename: string, options: FSWatchOptions, listener: FSWatchCallback): IFSWatcher
  // watch(filename: string, listener: FSWatchCallback): IFSWatcher
  // watch(filename: string, optionsOrListener: FSWatchOptions | FSWatchCallback, listener?: FSWatchCallback): IFSWatcher {
  //   // For simplicity, return a dummy watcher that does nothing
  //   return {
  //     close: () => { },
  //   }
  // }
}

// export enum FileSystemType {
//   OPFS = "opfs",
//   NFS = "nfs",
// }

// export async function getFsRootHandle(fsType: FileSystemType) {
//   let dirHandle: FileSystemDirectoryHandle

//   switch (fsType) {
//     case FileSystemType.NFS:
//       // how it works https://developer.chrome.com/blog/persistent-permissions-for-the-file-system-access-api
//       dirHandle = await getIndexedDBValue("kv", "localPath")
//       break
//     case FileSystemType.OPFS:
//     default:
//       dirHandle = await navigator.storage.getDirectory()
//       break
//   }
//   return dirHandle
// }

// export async function getExternalFolderHandle(name: string) {
//   const externalFolders = await getIndexedDBValue<FileSystemDirectoryHandle[]>(
//     "kv",
//     "externalFolders",
//   )
//   const dirHandle = externalFolders.find(dir => dir.name === name)
//   return dirHandle
// }

// const adapterSymbol = Symbol("adapter")

// function hasAdapterSymbol(obj: any): boolean {
//   const symbols = Object.getOwnPropertySymbols(obj)
//   return symbols.some(symbol => symbol.toString() === adapterSymbol.toString())
// }

// /**
//  * get DirHandle for a given path list
//  * we read config from indexeddb to decide which file system to use
//  * there are two file systems:
//  * 1. opfs: origin private file system. store files in web.
//  * 2. nfs: Native File System. store files in local file system.
//  * @param _paths path list just like ["root", "dir1", "dir2"]
//  * @param rootDirHandle we can pass rootDirHandle to avoid reading from indexeddb
//  * @returns
//  */
// export async function getDirHandle(_paths: string[], rootDirHandle?: FileSystemDirectoryHandle) {
//   const paths = [..._paths]
//   let dirHandle: FileSystemDirectoryHandle
//   if (rootDirHandle) {
//     dirHandle = rootDirHandle
//   }
//   else {
//     const fsType: FileSystemType = await getIndexedDBValue("kv", "fs")
//     dirHandle = await getFsRootHandle(fsType)
//   }
//   for (const path of paths) {
//     dirHandle = await dirHandle.getDirectoryHandle(path, { create: true })
//   }
//   return dirHandle
// }

// /**
//  * eidos fs structure:
//  * - spaces
//  *  - space1
//  *    - db.sqlite3
//  *    - files
//  *      - 1234567890.png
//  *      - 0987654321.png
//  *  - space2
//  *    - db.sqlite3
//  *
//  * spaces
//  * - what is a space? a space is a folder that contains a sqlite3 database, default name is db.sqlite3.
//  * - one space is one database.
//  *
//  * files
//  * - files is a folder that contains all static files, such as images, videos, etc.
//  * - when user upload a file, it will be saved in this folder. hash will be used as file name. e.g. 1234567890.png
//  */

// export class EidosFileSystemManager {
//   rootDirHandle: FileSystemDirectoryHandle | undefined
//   constructor(rootDirHandle?: FileSystemDirectoryHandle) {
//     if (rootDirHandle) {
//       this.rootDirHandle = rootDirHandle
//     }
//   }

//   isSameEntry = async (dirHandle: FileSystemDirectoryHandle) => {
//     return this.rootDirHandle?.isSameEntry(dirHandle)
//   }

//   getDirHandle = async (paths: string[]) => {
//     return getDirHandle(paths, this.rootDirHandle)
//   }

//   walk = async (_paths: string[]): Promise<string[][]> => {
//     const dirHandle = await getDirHandle(_paths, this.rootDirHandle)
//     const paths = []
//     const rootDirHandle = await getDirHandle([], this.rootDirHandle)
//     for await (const entry of (dirHandle as any).values()) {
//       if (entry.kind === "file") {
//         const path = await (this.rootDirHandle || rootDirHandle).resolve(entry)
//         paths.push(path)
//       }
//       else if (entry.kind === "directory") {
//         const subPaths: any = await this.walk([..._paths, entry.name])
//         paths.push(...subPaths)
//       }
//     }
//     return paths
//   }

//   copyFile = async (_paths: string[], targetFs: EidosFileSystemManager) => {
//     // copy file to target fs
//     const paths = [..._paths]
//     if (paths.length === 0) {
//       throw new Error("paths can't be empty")
//     }
//     const file = await this.getFile(paths)
//     const targetPaths = paths.slice(0, -1)
//     await targetFs.addFile(targetPaths, file)
//   }

//   copyTo = async (
//     targetFs: EidosFileSystemManager,
//     options?: {
//       ignoreSqlite?: boolean
//     },
//     cb?: (data: { current: number, total: number, msg: string }) => void,
//   ) => {
//     const paths = await this.walk([])
//     const targetPaths = await targetFs.walk([])
//     const targetPathsSet = new Set(targetPaths.map(p => p.join("/")))

//     const total = paths.length
//     for (const path of paths) {
//       const current = paths.indexOf(path) + 1
//       // ignore .opfs-sahpool
//       if (path[0] === ".opfs-sahpool") {
//         cb?.({
//           current,
//           total,
//           msg: "ignore .opfs-sahpool",
//         })
//         continue
//       }

//       if (path[path.length - 1] === "db.sqlite3") {
//         if (options?.ignoreSqlite) {
//           cb?.({
//             current,
//             total,
//             msg: "ignore db.sqlite3",
//           })
//           continue
//         }
//         else {
//           // if target fs is nfs, we need to copy sqlite file every time
//           await this.copyFile(path, targetFs)
//           cb?.({
//             current,
//             total,
//             msg: `copying ${path.join("/")}`,
//           })
//         }
//       }

//       // check if file exists
//       if (targetPathsSet.has(path.join("/"))) {
//         cb?.({
//           current,
//           total,
//           msg: `file exists ${path.join("/")}`,
//         })
//         continue
//       }
//       await this.copyFile(path, targetFs)
//       cb?.({
//         current,
//         total,
//         msg: `copying ${path.join("/")}`,
//       })
//     }
//     console.log("copy done")
//   }

//   getFileUrlByPath = (path: string, replaceSpace?: string) => {
//     const paths = path.split("/").slice(1)
//     if (replaceSpace) {
//       paths[0] = replaceSpace
//     }
//     return `/${paths.join("/")}`
//   }

//   getFileByURL = async (url: string) => {
//     const path = new URL(url).pathname
//     const parentPaths = path.split("/").slice(0, -1).filter(Boolean)
//     const parentDirHandle = await getDirHandle(
//       ["spaces", ...parentPaths],
//       this.rootDirHandle,
//     )
//     const filename = path.split("/").pop()
//     const realFilename = decodeURIComponent(filename!)
//     const fileHandle = await parentDirHandle.getFileHandle(realFilename)
//     return fileHandle.getFile()
//   }

//   getFileByPath = async (path: string) => {
//     const paths = path.split("/")
//     const file = await this.getFile(paths)
//     return file
//   }

//   listDir = async (_paths: string[]) => {
//     const dirHandle = await getDirHandle(_paths, this.rootDirHandle)
//     const entries: FileSystemFileHandle[] = []
//     for await (const entry of (dirHandle as any).values()) {
//       entries.push(entry)
//     }
//     return entries
//   }

//   updateOrCreateDocFile = async (_paths: string[], content: string) => {
//     const paths = [..._paths]
//     if (paths.length === 0) {
//       throw new Error("paths can't be empty")
//     }
//     const filename = paths.pop()
//     const dirHandle = await getDirHandle(paths, this.rootDirHandle)
//     const fileHandle = await dirHandle.getFileHandle(filename!, {
//       create: true,
//     })
//     const writable = await (fileHandle as any).createWritable()
//     await writable.write(content)
//     await writable.close()
//     console.log("update doc file", filename)
//   }

//   checkFileExists = async (_paths: string[]) => {
//     const paths = [..._paths]
//     if (paths.length === 0) {
//       throw new Error("paths can't be empty")
//     }
//     const filename = paths.pop()
//     const dirHandle = await getDirHandle(paths, this.rootDirHandle)
//     try {
//       await dirHandle.getFileHandle(filename!)
//       return true
//     }
//     catch (e) {
//       return false
//     }
//   }

//   getFile = async (_paths: string[], options?: FileSystemGetFileOptions) => {
//     const paths = [..._paths.filter(Boolean)]
//     if (paths.length === 0) {
//       throw new Error("paths can't be empty")
//     }
//     const filename = paths.pop()
//     const dirHandle = await getDirHandle(paths, this.rootDirHandle)
//     const fileHandle = await dirHandle.getFileHandle(filename!, options)
//     const file = await fileHandle.getFile()
//     return file
//   }

//   getFileText = async (_paths: string[]) => {
//     const file = await this.getFile(_paths)
//     return await file.text()
//   }

//   getDocContent = async (_paths: string[]) => {
//     const file = await this.getFile(_paths)
//     return await file.text()
//   }

//   addDir = async (_paths: string[], dirName: string) => {
//     const paths = [..._paths]
//     if (paths.length === 0) {
//       throw new Error("paths can't be empty")
//     }
//     const dirHandle = await getDirHandle(paths, this.rootDirHandle)
//     const r = await dirHandle.getDirectoryHandle(dirName, { create: true })

//     // const path = await opfsRoot.resolve(r)
//   }

//   addFile = async (_paths: string[], file: File, fileId?: string) => {
//     const paths = [..._paths]
//     if (paths.length === 0) {
//       throw new Error("paths can't be empty")
//     }
//     const dirHandle = await getDirHandle(paths, this.rootDirHandle)
//     console.log("dirHandle", dirHandle)
//     // if fileId is provided, use it as file name
//     const fileExt = extension(file.type)
//     const filename = fileId ? `${fileId}.${fileExt}` : file.name
//     const fileHandle = await dirHandle.getFileHandle(filename, {
//       create: true,
//     })
//     const writable = await (fileHandle as any).createWritable()
//     await writable.write(file)
//     await writable.close()
//     // fileHandle get path
//     const rootDirHandle = await getDirHandle([], this.rootDirHandle)
//     const relativePath = await rootDirHandle.resolve(fileHandle)
//     console.log("relativePath", { rootDirHandle, fileHandle, relativePath })
//     return relativePath
//   }

//   deleteEntry = async (_paths: string[], isDir = false) => {
//     const paths = [..._paths]
//     if (paths.length === 0) {
//       throw new Error("paths can't be empty")
//     }
//     if (isDir) {
//       const dirHandle = await getDirHandle(paths, this.rootDirHandle)
//       // The remove() method is currently only implemented in Chrome. You can feature-detect support via 'remove' in FileSystemFileHandle.prototype.
//       await (dirHandle as any).remove({
//         recursive: true,
//       })
//     }
//     else {
//       const filename = paths.pop()
//       const dirHandle = await getDirHandle(paths, this.rootDirHandle)
//       await dirHandle.removeEntry(filename!)
//     }
//   }

//   renameFile = async (_paths: string[], newName: string) => {
//     const paths = [..._paths]
//     if (paths.length === 0) {
//       throw new Error("paths can't be empty")
//     }
//     const filename = paths.pop()
//     const dirHandle = await getDirHandle(paths, this.rootDirHandle)
//     const fileHandle = (await dirHandle.getFileHandle(filename!, {
//       create: true,
//     })) as any
//     await fileHandle.move(newName)
//   }
// }

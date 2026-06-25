import type { PiniaStore, ProtocolModels } from "@airalogy/shared/types"
import type { FileInterface, FileSystemItem } from "../types"
import type { AddItemPayload } from "../utils/file-tree"
import { useClosableMessage } from "@airalogy/composables"
import { DEFAULT_FILE_ID_NAME_MAP } from "@airalogy/shared"
import { arrayBufferToString, canEditAsText } from "@airalogy/shared/utils"
import { nanoid } from "nanoid"
import { defineStore } from "pinia"
import { parse, stringify } from "smol-toml"
import { ref, shallowRef } from "vue"
import { getRootPath } from "../composables/useFileUpload"
import {
  addItem as addItemToTree,
  findByFilename,
  findById,
  findByPath,
  removeItemById,
} from "../utils/file-tree"
import { DEFAULT_FILE_DATA, getProjectDataFromLocal, isFile, saveProjectData } from "../utils/filesystem"

export const PENDING_DIRECTORY = "$PENDING:DIRECTORY$"
export const PENDING_FILE = "$PENDING:FILE$"
export function prepareName(name: string) {
  return name.replaceAll(PENDING_DIRECTORY, "").replaceAll(PENDING_FILE, "")
}

export function isPending(path: string) {
  return path.endsWith(PENDING_DIRECTORY) || path.endsWith(PENDING_FILE)
}

// Version.py is deprecated - use protocol.toml instead
const DEPRECATED_VERSION_PY_WARNING = "version.py is deprecated. Please use protocol.toml for version information."

export const useUploadFileDataStore = defineStore("uploadFileData", () => {
  const fileData = ref<FileSystemItem[] | null>(null)
  const selected = ref("")
  const packageId = ref("")
  const showTemplateDialog = ref(false)
  const pendingProtocolInfo = ref<ProtocolModels.ProjectProtocolInfo | null>(null)

  const rootPath = ref("")
  const message = useClosableMessage()
  const uniqueFiles = computed(() => {
    return Object.fromEntries(Object.entries(DEFAULT_FILE_ID_NAME_MAP).map(([id, name]) => {
      return [`${rootPath.value}/${name}`, id]
    }))
  })

  function updateRootPath(pathList: string[]) {
    rootPath.value = getRootPath(pathList)
  }

  const uploadProtocolPackage = shallowRef<(id: string, data: (FileSystemItem)[]) => Promise<void>>(() => Promise.resolve())

  const downloadProtocolPackage = shallowRef<(id: string) => Promise<(FileSystemItem)[] | null>>(() => Promise.resolve(null))

  async function createInitialFileData(id: string, protocolInfo: ProtocolModels.ProjectProtocolInfo | null = null, template = { type: "basic", name: "Default Protocol", version: "0.1.0" }) {
    let newFileData: (FileSystemItem)[] = []

    if (template.type === "empty") {
      // For empty project, just create an empty array
      newFileData = []
    }
    else {
      // Start with a deep copy of DEFAULT_FILE_DATA
      const filesCopy = JSON.parse(JSON.stringify(DEFAULT_FILE_DATA)) as (FileSystemItem)[]

      // Make all files editable
      filesCopy.forEach((file) => {
        file.isEditable = true
      })

      // Update protocol.toml content with template values
      const tomlFile = filesCopy.find(file => file.id === "airalogy_toml_config")
      if (tomlFile && isFile(tomlFile)) {
        const version = template.version || "0.1.0"
        tomlFile.content = `[airalogy_protocol]\nversion = "${version}"\nname = "${template.name || "Default Protocol"}"\ndescription = "Protocol description"\n`
      }

      // Update protocol.aimd with template name
      const aimdFile = filesCopy.find(file => file.id === "airalogy_protocol")
      if (aimdFile && isFile(aimdFile)) {
        if (typeof aimdFile.content !== "string") {
          aimdFile.content = arrayBufferToString(aimdFile.content)
        }

        aimdFile.content = aimdFile.content?.replace("# AIMD Template", `# ${template.name}`) || ""
      }

      if (template.type === "basic") {
        // Use all files for basic template
        newFileData = filesCopy
      }
      else if (template.type === "custom") {
        // Only use protocol.toml for custom template
        newFileData = filesCopy.filter(file => file.id === "airalogy_toml_config")
      }
    }

    // Update the version if protocolInfo is available
    if (protocolInfo && protocolInfo.latest_version) {
      try {
        // Parse the current version
        const currentVersion = protocolInfo.latest_version
        const versionParts = currentVersion.split(".").map(Number)

        // Ensure it's a valid semver format
        if (versionParts.length === 3 && !versionParts.some(part => Number.isNaN(part))) {
          // Increment the minor version, reset patch to 0
          const newVersion = `${versionParts[0]}.${versionParts[1] + 1}.0`

          // First look for protocol.toml
          const tomlFileIndex = newFileData.findIndex(file => file.name === "protocol.toml")
          if (tomlFileIndex !== -1) {
            // Update version in protocol.toml
            const tomlFile = newFileData[tomlFileIndex]
            if (isFile(tomlFile)) {
              try {
                if (typeof tomlFile.content !== "string") {
                  tomlFile.content = arrayBufferToString(tomlFile.content)
                }

                // Parse existing TOML content
                const tomlData = parse(tomlFile.content || "") as Record<string, any>

                // Ensure airalogy_protocol section exists
                if (!tomlData.airalogy_protocol) {
                  tomlData.airalogy_protocol = {}
                }

                // Update version
                tomlData.airalogy_protocol.version = newVersion

                // Stringify back to TOML
                const updatedToml = stringify(tomlData)

                // Update file content
                newFileData[tomlFileIndex] = {
                  ...tomlFile,
                  content: updatedToml,
                }

                message.info(`Updated version to ${newVersion} in protocol.toml based on protocolInfo version ${currentVersion}`)
              }
              catch (error) {
                console.error("Error updating protocol.toml:", error)
              }
            }
          }
        }
      }
      catch (error) {
        console.error("Error updating version:", error)
      }
    }

    // Save the updated project data
    await saveProjectData(id, newFileData, uploadProtocolPackage.value)
    fileData.value = newFileData
    updateRootPath(newFileData.map(({ path }) => path))

    return newFileData
  }

  function hasProtocolFiles(projectData: (FileSystemItem)[]): boolean {
    // Check if the project has essential protocol files
    const hasProtocolToml = projectData.some(file => file.name === "protocol.toml")
    return hasProtocolToml
  }

  async function createFromTemplate(template: { type: string, name: string, version: string }) {
    if (!packageId.value) {
      message.error("Package ID is not set")
      return
    }

    const id = packageId.value
    const newFileData = await createInitialFileData(id, pendingProtocolInfo.value, template)

    fileData.value = newFileData
    updateRootPath(newFileData.map(item => item.path))

    await saveProjectData(id, newFileData, uploadProtocolPackage.value)
    showTemplateDialog.value = false
    pendingProtocolInfo.value = null
  }

  async function initFileData(id: string, protocolInfo: ProtocolModels.ProjectProtocolInfo | null = null, resist = false) {
    packageId.value = id
    pendingProtocolInfo.value = protocolInfo

    try {
      // Get the project data using the centralized function
      const projectData = await getProjectDataFromLocal(id, downloadProtocolPackage.value)

      // Convert project file data to DirectoryInterface format
      if (projectData) {
        // Check if the project has essential protocol files
        if (!hasProtocolFiles(projectData)) {
          // We'll return null to signal the caller to redirect to landing page
          // instead of showing dialog directly
          return null
        }

        fileData.value = projectData
        updateRootPath(projectData.map(item => item.path))

        // Check if migration from version.py to protocol.toml is needed
        const hasVersionPy = projectData.some(file => file.name === "version.py")
        const hasProtocolToml = projectData.some(file => file.name === "protocol.toml")

        if (hasVersionPy && !hasProtocolToml) {
          // Attempt to migrate from version.py to protocol.toml
          await migrateFromVersionPyToToml()
        }

        return projectData
      }

      // No project data, return null to signal the caller to redirect to landing page
      return null
    }
    catch (error) {
      console.error("Error initializing file data:", error)
      return null
    }
  }

  async function clearFileData(resist = false, id = "") {
    if (resist && id) {
      try {
        // Save the updated project data
        await saveProjectData(id, fileData.value || [], uploadProtocolPackage.value)
      }
      catch (error) {
        console.error("Error saving file data:", error)
      }
    }
    else {
      // Reset to default when not persisting
      fileData.value = []
    }
  }

  function setSelected(newSelected: string) {
    selected.value = newSelected
  }

  function setFileData(newFileData: (FileSystemItem)[] | null) {
    fileData.value = newFileData
  }

  function removeFileById(id: string) {
    if (fileData.value) {
      removeItemById(fileData.value, id)
    }
  }
  function getFileById(id: string): FileInterface | null {
    if (!fileData.value)
      return null

    const file = findById(fileData.value, id)

    return isFile(file) ? file : null
  }

  function getFileByFilename(filename: string): FileInterface | null {
    if (!fileData.value)
      return null

    const file = findByFilename(fileData.value, filename)
    return isFile(file) ? file : null
  }

  function getFileByPath(path: string): FileSystemItem | null {
    if (fileData.value) {
      return findByPath(fileData.value, path)
    }
    return null
  }

  function addFileOrFolder(payload: AddItemPayload,
  ) {
    if (!fileData.value) {
      fileData.value = []
    }

    const parent = payload.parent || {
      id: "root",
      name: "",
      path: "",
      kind: "directory",
      children: fileData.value,
    }

    addItemToTree(fileData.value, { ...payload, parent, rootPath: rootPath.value })
  }

  async function updateFileItem(id: string, updatedProperties: Partial<FileSystemItem>, save = false) {
    if (!fileData.value) {
      fileData.value = []
    }

    let result: FileSystemItem | boolean = true
    const item = findById(fileData.value, id)
    if (item) {
      const { name, path } = updatedProperties
      const isDuplicated = fileData.value.some(it => it !== item && it.path === path && it.name === name)
      if (isDuplicated) {
        item.status = "error"
        message.error(`Name ${name} is duplicated.`)
        return false
      }

      if (path && uniqueFiles.value[path]) {
        Object.assign(item, { ...updatedProperties, id: uniqueFiles.value[path] })
        result = item
      }
      else {
        Object.assign(item, updatedProperties)
        result = item
      }
    }
    else {
      const { name } = updatedProperties
      if (name) {
        addFileOrFolder({ ...updatedProperties, status: "pending" } as AddItemPayload)
      }
    }

    if (save) {
      await saveProjectData(packageId.value, fileData.value, uploadProtocolPackage.value)
    }

    return result
  }

  /**
   * Gets the current version from the version.py file in fileData
   * @returns The version string (e.g., "1.0.0") or null if not found
   */
  function getVersionFromFileData(): string | null {
    if (!fileData.value) {
      return null
    }

    // First try to get version from protocol.toml
    const tomlFile = getFileByFilename("protocol.toml")
    if (tomlFile && isFile(tomlFile) && tomlFile.content) {
      try {
        if (typeof tomlFile.content !== "string") {
          tomlFile.content = arrayBufferToString(tomlFile.content)
        }

        const tomlData = parse(tomlFile.content) as Record<string, any>
        if (tomlData.airalogy_protocol && tomlData.airalogy_protocol.version) {
          console.log("[Upload File Store] Found version in protocol.toml:", tomlData.airalogy_protocol.version)
          return tomlData.airalogy_protocol.version
        }
      }
      catch (error) {
        console.error("Error parsing protocol.toml:", error)
      }
    }

    // Fallback to version.py for backward compatibility
    const versionFile = fileData.value.find(file => file.name === "version.py")
    if (!versionFile || !isFile(versionFile) || !versionFile.content) {
      console.log("[Upload File Store] Version information not found in either protocol.toml or version.py")
      return null
    }

    // Show deprecation warning when version.py is used
    console.warn(DEPRECATED_VERSION_PY_WARNING)
    message.warning(DEPRECATED_VERSION_PY_WARNING)

    if (typeof versionFile.content !== "string") {
      versionFile.content = arrayBufferToString(versionFile.content)
    }
    // Extract version from the file content (VERSION = "x.y.z")
    const versionMatch = versionFile.content.match(/VERSION\s*=\s*"([^"]+)"/)
    if (versionMatch && versionMatch[1]) {
      console.log("[Upload File Store] Found version in version.py:", versionMatch[1])
      return versionMatch[1]
    }

    console.log("[Upload File Store] Failed to extract version from version.py")
    return null
  }

  /**
   * Updates the version in the protocol.toml file in fileData
   * @param newVersion The new version string (e.g., "1.0.0")
   * @param save Whether to save the changes to storage
   * @returns A promise that resolves to true if successful, false otherwise
   */
  async function updateVersionInFileData(newVersion: string, save = true): Promise<boolean> {
    if (!fileData.value) {
      message.error("File data not initialized")
      return false
    }

    try {
      // Validate version format
      const versionParts = newVersion.split(".").map(Number)
      if (versionParts.length !== 3 || versionParts.some(part => Number.isNaN(part))) {
        message.error("Invalid version format. Expected x.y.z")
        return false
      }

      // Find the protocol.toml file
      let tomlFileIndex = fileData.value.findIndex(file => file.name === "protocol.toml")

      // If protocol.toml doesn't exist, create it
      if (tomlFileIndex === -1) {
        const newTomlFile: FileInterface = {
          id: nanoid(),
          name: "protocol.toml",
          path: `${rootPath.value}/protocol.toml`,
          kind: "file",
          status: "success",
          content: `[airalogy_protocol]\nversion = "${newVersion}"\nname = "Default Protocol"\ndescription = "Default protocol description"\n`,
          isRemovable: false,
          isEditable: true,
        }

        fileData.value.push(newTomlFile)
        tomlFileIndex = fileData.value.length - 1
      }
      else {
        // Update existing protocol.toml
        const tomlFile = fileData.value[tomlFileIndex]
        if (isFile(tomlFile)) {
          try {
            if (typeof tomlFile.content !== "string") {
              tomlFile.content = arrayBufferToString(tomlFile.content)
            }
            // Parse existing TOML content
            const tomlData = parse(tomlFile.content || "") as Record<string, any>

            // Ensure protocol section exists
            if (!tomlData.airalogy_protocol) {
              tomlData.airalogy_protocol = {}
            }

            // Update version
            tomlData.airalogy_protocol.version = newVersion

            // Stringify back to TOML
            const updatedToml = stringify(tomlData)

            // Update file content
            fileData.value[tomlFileIndex] = {
              ...tomlFile,
              content: updatedToml,
            }
          }
          catch (error) {
            console.error("Error parsing/updating protocol.toml:", error)
            message.error("Failed to update protocol.toml")
            return false
          }
        }
      }

      // Also update version.py for backward compatibility
      const versionFileIndex = fileData.value.findIndex(file => file.name === "version.py")
      if (versionFileIndex !== -1) {
        const versionFile = fileData.value[versionFileIndex]
        if (isFile(versionFile)) {
          fileData.value[versionFileIndex] = {
            ...versionFile,
            content: `VERSION = "${newVersion}"`,
          }
        }
      }

      // Save to localStorage if requested
      if (save) {
        await saveProjectData(packageId.value, fileData.value, uploadProtocolPackage.value)
      }

      message.success(`Version updated to ${newVersion}`)
      return true
    }
    catch (error) {
      console.error("Error updating version:", error)
      message.error("Failed to update version")
      return false
    }
  }

  /**
   * Increments the version according to semantic versioning rules
   * @param type The version part to increment: "major", "minor", or "patch"
   * @param save Whether to save the changes to storage
   * @returns A promise that resolves to the new version string if successful, null otherwise
   */
  async function incrementVersion(type: "major" | "minor" | "patch", save = true): Promise<string | null> {
    const currentVersion = getVersionFromFileData()
    if (!currentVersion) {
      message.error("Could not determine current version")
      return null
    }

    const parts = currentVersion.split(".").map(Number)
    if (parts.length !== 3 || parts.some(part => Number.isNaN(part))) {
      message.error("Invalid version format")
      return null
    }

    switch (type) {
      case "major":
        parts[0]++
        parts[1] = 0
        parts[2] = 0
        break
      case "minor":
        parts[1]++
        parts[2] = 0
        break
      case "patch":
        parts[2]++
        break
    }

    const newVersion = parts.join(".")
    const success = await updateVersionInFileData(newVersion, save)
    return success ? newVersion : null
  }

  /**
   * Creates a protocol.toml file from the version.py file if it exists
   * @returns A promise that resolves to true if migration successful, false otherwise
   */
  async function migrateFromVersionPyToToml(): Promise<boolean> {
    if (!fileData.value) {
      message.error("File data not initialized")
      return false
    }

    try {
      // Check if protocol.toml already exists
      const existingToml = fileData.value.find(file => file.name === "protocol.toml")
      if (existingToml) {
        return true // No migration needed
      }

      // Find version.py
      const versionFile = fileData.value.find(file => file.name === "version.py")
      if (!versionFile || !isFile(versionFile) || !versionFile.content) {
        return false // No version.py to migrate from
      }

      if (typeof versionFile.content !== "string") {
        versionFile.content = arrayBufferToString(versionFile.content)
      }
      // Extract version from version.py
      const versionMatch = versionFile.content.match(/VERSION\s*=\s*"([^"]+)"/)
      if (!versionMatch || !versionMatch[1]) {
        message.error("Failed to extract version from version.py")
        return false
      }

      const version = versionMatch[1]

      // Create new protocol.toml
      const newTomlFile: FileInterface = {
        id: nanoid(),
        name: "protocol.toml",
        path: `${rootPath.value}/protocol.toml`,
        kind: "file",
        status: "success",
        content: `[airalogy_protocol]\nversion = "${version}"\nname = "Default Protocol"\ndescription = "Default protocol description"\n`,
        isRemovable: false,
        isEditable: true,
      }

      fileData.value.push(newTomlFile)
      message.success(`Migrated version "${version}" from version.py to protocol.toml`)

      // Save changes
      await saveProjectData(packageId.value, fileData.value, uploadProtocolPackage.value)

      return true
    }
    catch (error) {
      console.error("Error migrating from version.py to protocol.toml:", error)
      message.error("Failed to migrate from version.py to protocol.toml")
      return false
    }
  }

  return {
    packageId,
    fileData,
    rootPath,
    selected,
    showTemplateDialog,
    pendingProtocolInfo,
    initFileData,
    createInitialFileData,
    clearFileData,
    setSelected,
    setFileData,
    removeFileById,
    addFileOrFolder,
    updateFileItem,
    getFileByFilename,
    getFileById,
    getFileByPath,
    updateRootPath,
    createFromTemplate,
    // Add new version-related functions
    getVersionFromFileData,
    updateVersionInFileData,
    incrementVersion,
    migrateFromVersionPyToToml,
    // Add new file handling functions
    createFileBlob,
    revokeFileBlob,
    updateFileWithBlob,
    uploadProtocolPackage,
    downloadProtocolPackage,
  }
})

export type UploadFileStore = PiniaStore<typeof useUploadFileDataStore>
/**
 * Creates a blob URL for non-text files
 * @param file The file to create a blob URL for
 * @returns The blob URL string
 */
function createFileBlob(file: File | Blob): string {
  return URL.createObjectURL(file)
}

/**
 * Revokes a blob URL to free up memory
 * @param url The blob URL to revoke
 */
function revokeFileBlob(url: string): void {
  URL.revokeObjectURL(url)
}

/**
 * Updates a file item with blob URL for non-text files
 * @param fileItem The file item to update
 * @param file The file object to create blob from
 * @returns The updated file item
 */
function updateFileWithBlob(fileItem: FileInterface, file: File): FileInterface | Promise<FileInterface> {
  // Only create blob for non-text files
  const shouldCreateBlob = !canEditAsText(fileItem.name)

  if (shouldCreateBlob) {
    // Clean up existing blob URL if it exists
    if (fileItem.fileUrl) {
      revokeFileBlob(fileItem.fileUrl)
    }

    // Create new blob URL
    fileItem.fileUrl = createFileBlob(file)
    fileItem.fileSize = file.size
    fileItem.fileType = file.type
    fileItem.content = "" // Clear text value for non-text files
    return fileItem
  }
  else {
    // For text files, read as text
    return new Promise((resolve) => {
      const reader = new FileReader()
      reader.onload = (e) => {
        fileItem.content = e.target?.result as string
        fileItem.fileUrl = undefined // Clear blob URL for text files
        resolve(fileItem)
      }
      reader.readAsText(file)
    })
  }
}

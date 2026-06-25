import type { ProtocolDocument } from "../types/document"
import type { WebContainer } from "../types/fileSystem"
import { nanoid } from "nanoid"
import { defineStore, storeToRefs } from "pinia"
import { ref, type Ref } from "vue"
import { rm, writeDirByLocal, writeFile } from "../utils"
import { useUploadFileDataStore } from "./uploadFileDataStore"
import { useWebContainerStore } from "./webContainerStore"

// Default path for storing documents
export const DEFAULT_DOCUMENTS_PATH = ".documents"

export const useProtocolDocumentsStore = defineStore("protocol-documents", () => {
  // State
  const documents = ref<ProtocolDocument[]>([])
  const isProcessing = ref(false)
  const activeDocumentId = ref<string | null>(null)

  // Helper function to safely get the WebContainer instance
  const webContainerStore = useWebContainerStore()
  const uploadFileDataStore = useUploadFileDataStore()
  const { webContainerInstance } = storeToRefs(webContainerStore) as { webContainerInstance: Ref<WebContainer | null> }
  const documentDirPath = computed(() => `${uploadFileDataStore.rootPath}/${DEFAULT_DOCUMENTS_PATH}`)
  const postUploadReferenceAssets = shallowRef<(...args: any[]) => Promise<any>>(() => Promise.resolve())

  // Helper to ensure a document path exists
  async function ensureDocumentsDirectory(): Promise<boolean> {
    const container = webContainerInstance.value
    if (!container)
      return false

    try {
      // Create the directory structure
      const dirStructure = {
        path: documentDirPath.value,
        kind: "directory" as const,
        children: [],
      }

      await writeDirByLocal(dirStructure, container)
      return true
    }
    catch (error) {
      console.error("Failed to create documents directory:", error)
      return false
    }
  }

  // Get a full path for a document
  function getDocumentPath(docNameOrPath: string): string {
    // If the path already includes the default path, return it as is
    if (docNameOrPath.startsWith(`${documentDirPath.value}/`)) {
      return docNameOrPath
    }

    // Otherwise, join the default path with the document name
    return `${documentDirPath.value}/${docNameOrPath}`
  }

  // Actions
  async function addDocument(doc: Omit<ProtocolDocument, "id" | "createdAt" | "status">) {
    const newDoc: ProtocolDocument = {
      ...doc,
      id: `doc-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
      createdAt: new Date(),
      status: "init",
    }
    documents.value.push(newDoc)
    await writeDocumentToFileSystemById(newDoc.id, newDoc.path)
    return newDoc.id
  }

  function updateDocumentStatusById(id: string, status: ProtocolDocument["status"], metadata?: Record<string, any>) {
    const doc = getDocumentById(id)
    if (doc) {
      updateDocumentStatus(doc, status, metadata)
    }
  }

  function updateDocumentStatus(doc: ProtocolDocument, status: ProtocolDocument["status"], metadata?: Record<string, any>) {
    doc.status = status
    if (metadata) {
      doc.metadata = { ...doc.metadata, ...metadata }
    }
  }

  /**
   * Updates a document's status and optionally persists it to the filesystem
   * @param id Document ID to update
   * @param status New status to set
   * @param options Configuration options
   * @returns Promise that resolves when the operation completes
   */
  async function updateDocumentStatusAndSaveById(
    id: string,
    status: ProtocolDocument["status"],
    options: {
      metadata?: Record<string, any>
      writeToFileSystem?: boolean
      path?: string
    } = {},
  ): Promise<boolean> {
    const { metadata, writeToFileSystem = true, path } = options

    // Update in memory
    updateDocumentStatusById(id, status, metadata)

    // Write to filesystem if requested
    if (writeToFileSystem) {
      try {
        await writeDocumentToFileSystemById(id, path)
        return true
      }
      catch (error) {
        console.error(`Failed to write document ${id} to filesystem:`, error)
        // Revert status to error if filesystem write fails
        updateDocumentStatusById(id, "error", {
          error: error instanceof Error ? error.message : String(error),
        })
        return false
      }
    }

    return true
  }
  async function updateDocumentStatusAndSave(
    doc: ProtocolDocument,
    status: ProtocolDocument["status"],
    options: {
      metadata?: Record<string, any>
      writeToFileSystem?: boolean
      path?: string
    } = {},
  ): Promise<boolean> {
    const { metadata, writeToFileSystem = true, path } = options

    // Update in memory
    updateDocumentStatus(doc, status, metadata)

    // Write to filesystem if requested
    if (writeToFileSystem) {
      try {
        await writeDocumentToFileSystem(doc, path || doc.path)
        return true
      }
      catch (error) {
        console.error(`Failed to write document ${doc.id} to filesystem:`, error)
        // Revert status to error if filesystem write fails
        updateDocumentStatus(doc, "error", {
          error: error instanceof Error ? error.message : String(error),
        })
        return false
      }
    }

    return true
  }

  async function removeDocument(id: string) {
    const doc = getDocumentById(id)
    if (doc?.path) {
      // Remove from file system if path is set
      const container = webContainerInstance.value
      if (container) {
        await rm(doc.path, container)
      }
    }
    documents.value = documents.value.filter(doc => doc.id !== id)
  }

  function clearDocuments() {
    // Remove all documents from file system
    const container = webContainerInstance.value
    if (container) {
      documents.value.forEach((doc) => {
        if (doc.path) {
          rm(doc.path, container)
        }
      })
    }
    documents.value = []
  }

  function setActiveDocument(id: string | null) {
    activeDocumentId.value = id
  }

  function updateDocumentModelId(id: string, modelId: string) {
    const doc = getDocumentById(id)
    if (doc) {
      doc.modelId = modelId
    }
  }

  function getDocumentByModelId(modelId: string) {
    return documents.value.find(doc => doc.modelId === modelId)
  }
  function getDocumentById(id: string) {
    return documents.value.find(doc => doc.id === id)
  }

  function updateDocumentContentById(id: string, content: string) {
    const doc = getDocumentById(id) || getDocumentByModelId(id)
    if (doc) {
      updateDocumentContent(doc, content)
    }
  }

  function updateDocumentContent(doc: ProtocolDocument, content: string) {
    doc.status = "modified"
    doc.content = content

    if (content) {
      doc.size = content.length
    }
    else {
      doc.size = 0
    }

    // Write to file system if path is set
    if (doc.path) {
      const container = webContainerInstance.value
      if (container) {
        writeFile(doc.path, content, container)
      }
    }
  }

  // New function to write document to file system
  async function writeDocumentToFileSystemById(id: string, path?: string) {
    const doc = getDocumentById(id)
    if (!doc) {
      return false
    }

    // Use the provided path or generate one based on document name
    const filePath = path || getDocumentPath(doc.name)
    if (doc.path !== filePath) {
      doc.path = filePath
    }

    return await writeDocumentToFileSystem(doc, filePath)
  }

  async function writeDocumentToFileSystem(doc: ProtocolDocument, path: string) {
    const container = webContainerInstance.value
    if (!container) {
      return false
    }

    // Ensure documents directory exists
    await ensureDocumentsDirectory()
    try {
      await writeFile(path, doc.content || "", container)

      return true
    }
    catch (error) {
      console.error("Failed to write document to file system:", error)
      return false
    }
  }

  // New function to write all documents to file system
  async function writeAllDocumentsToFileSystem(basePath?: string) {
    const container = webContainerInstance.value
    if (!container)
      return false

    // Ensure documents directory exists
    await ensureDocumentsDirectory()

    // Use provided base path or default
    const documentBasePath = basePath || documentDirPath.value

    for (const doc of documents.value) {
      if (doc.content) {
        const path = `${documentBasePath}/${doc.name}`.replace(/\/\//g, "/")

        // Update document with path
        doc.path = path
        doc.status = "success"
        try {
          await writeFile(path, doc.content, container)
        }
        catch (error) {
          console.error("Failed to write all documents to file system:", error)
          doc.status = "error"
          return false
        }
      }
    }

    return true
  }

  // New function to create directory structure and write documents
  async function writeDocumentsToDirectory(directoryPath?: string, docs: ProtocolDocument[] = documents.value) {
    const container = webContainerInstance.value
    if (!container)
      return false

    // Use provided directory path or default
    const documentBasePath = directoryPath || documentDirPath.value

    try {
      // Create directory structure
      const dirStructure = {
        path: documentBasePath,
        kind: "directory" as const,
        children: docs.map(doc => ({
          path: `${documentBasePath}/${doc.name}`.replace(/\/\//g, "/"),
          kind: "file" as const,
          value: doc.content || "",
        })),
      }

      await writeDirByLocal(dirStructure, container)

      // Update documents with paths
      for (const doc of docs) {
        const path = `${documentBasePath}/${doc.name}`.replace(/\/\//g, "/")
        const targetDoc = getDocumentById(doc.id)
        if (targetDoc) {
          targetDoc.path = path
        }
      }

      return true
    }
    catch (error) {
      console.error("Failed to write documents to directory:", error)
      return false
    }
  }

  async function uploadDocument(id: string, protocolId?: string | number) {
    const doc = getDocumentById(id)
    if (!doc || !doc.content)
      return

    if (!protocolId && !doc.protocolId) {
      throw new Error("Protocol ID is required for uploading documents")
    }

    try {
      updateDocumentStatusById(id, "init")

      // Create a File object from the content
      const file = new File([doc.content], doc.name, { type: doc.type })

      const response = await postUploadReferenceAssets.value(protocolId || doc.protocolId!, { file })

      if (response.data) {
        // Update with uploaded data
        const targetDoc = getDocumentById(id)
        if (targetDoc) {
          targetDoc.status = "uploaded"
          targetDoc.airalogyFileId = response.data.airalogy_file_id
          targetDoc.url = response.data.url
          if (!targetDoc.metadata) {
            targetDoc.metadata = {}
          }
          targetDoc.metadata.uploadedAt = new Date()
        }

        await writeDocumentToFileSystemById(id, `${DEFAULT_DOCUMENTS_PATH}/${doc.name}`)
        return true
      }
      throw new Error("Upload failed")
    }
    catch (error) {
      updateDocumentStatusById(id, "error", { error: String(error) })
      return false
    }
  }

  async function uploadAllDocuments(protocolId?: string | number) {
    isProcessing.value = true

    try {
      const uploadPromises = documents.value
        .filter(doc => doc.status !== "uploaded")
        .map(doc => uploadDocument(doc.id, protocolId))
      await Promise.all(uploadPromises)
    }
    finally {
      isProcessing.value = false
    }
  }

  async function removeAllDocuments() {
    // Remove all documents from file system first
    const container = webContainerInstance.value
    if (container) {
      documents.value.forEach((doc) => {
        if (doc.path) {
          rm(doc.path, container)
        }
      })
    }
    documents.value = []
  }

  async function updateDocumentAndSaveById(id: string, updatedProperties: Partial<ProtocolDocument>) {
    const doc = getDocumentById(id)
    const container = webContainerInstance.value
    if (!doc || !container) {
      return
    }

    await updateDocumentAndSave(doc, updatedProperties)
  }

  async function updateDocumentAndSave(doc: ProtocolDocument, updatedProperties: Partial<ProtocolDocument>) {
    Object.assign(doc, updatedProperties)

    await writeDocumentToFileSystem(doc, doc.path)
  }

  async function initDocuments() {
    const container = webContainerInstance.value
    if (!container)
      return

    try {
      const dir = await container.fs.readdir(documentDirPath.value, { withFileTypes: true })

      documents.value = await Promise.all(dir.map(async (item): Promise<ProtocolDocument> => {
        const { name } = item
        const content = await container.fs.readFile(`${documentDirPath.value}/${name}`)
        return {
          name,
          id: nanoid(),
          content: content.toString(),
          size: content.length,
          type: "text",
          status: "success",
          createdAt: new Date(),
          path: `${documentDirPath.value}/${name}`,
        }
      }))
    }
    catch (error) {
      await container.fs.mkdir(documentDirPath.value)
      documents.value = []
    }
  }
  return {
    documents,
    activeDocumentId,
    addDocument,
    updateDocumentStatusById,
    updateDocumentStatus,
    updateDocumentStatusAndSaveById,
    updateDocumentStatusAndSave,
    removeDocument,
    clearDocuments,
    setActiveDocument,
    updateDocumentModelId,
    getDocumentByModelId,
    updateDocumentContentById,
    updateDocumentContent,
    ensureDocumentsDirectory,
    writeDocumentToFileSystemById,
    writeDocumentToFileSystem,
    writeAllDocumentsToFileSystem,
    writeDocumentsToDirectory,
    uploadDocument,
    uploadAllDocuments,
    removeAllDocuments,
    initDocuments,
    getDocumentPath,
    updateDocumentAndSaveById,
    updateDocumentAndSave,
    isProcessing,
    getDocumentById,
    documentDirPath,
  }
})

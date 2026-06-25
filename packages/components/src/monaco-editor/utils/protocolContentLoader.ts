import type { ProtocolData, ProtocolPackageFileId } from "@airalogy/shared/constants"
import type { ProtocolMetaData } from "@airalogy/shared/types/models/protocol.js"
import type { Ref } from "vue"
import type { UploadContent, UploadModel, ZipUpload } from "../types/upload"
import { arrayBufferToString } from "@airalogy/shared"
import { parse } from "smol-toml"

export async function convertContentToProtocol(acc: ProtocolData, path: string, v: Uint8Array, root: string) {
  try {
    let key: ProtocolPackageFileId | undefined
    if (path === `${root}model.py`) {
      key = "model"
    }
    else if (path === `${root}protocol.aimd`) {
      key = "protocol"
    }
    else if (path === `${root}assigner.py`) {
      key = "assigner"
    }

    if (!key) {
      return
    }

    const content = arrayBufferToString(v)
    acc[key] = content
    // else if (k === `${root}version.py`) {
    //   acc.metadata.version = parseVersion(arrayBufferToString(v))
    // }
  }
  catch (e) {
    //
  }
  finally {
    // eslint-disable-next-line no-unsafe-finally
    return acc
  }
}

/**
 * Handles loading protocol content from a ZIP file
 *
 * @param content The uploaded content (ZIP file)
 * @param uploadModel Reference to the upload model that should be updated
 * @param protocolData Reference to the protocol data that should be updated
 * @param packageContent Reference to store the package content
 */
export function handleContentLoaded(
  content: UploadContent,
  uploadModel: Ref<UploadModel>,
  protocolData: Ref<ProtocolData | null>,
  packageContent: Ref<ZipUpload | null>,
): void {
  if (content.type !== "zip")
    return

  // Update package content
  packageContent.value = content

  const { items, root } = content.content

  // Extract protocol data using utility function
  const models = items.reduce((acc, item) => {
    const { path, content: itemContent } = item
    if (itemContent) {
      convertContentToProtocol(acc, path, itemContent, root)
    }
    return acc
  }, { model: "", assigner: "", protocol: "", toml_config: "", metadata: {} } as ProtocolData)

  // Set protocol data
  protocolData.value = models

  // Find the TOML file to set in upload model
  const tomlFile = items.find(item => item.path === `${root}protocol.toml`)
  if (tomlFile?.content) {
    const tomlContent = arrayBufferToString(tomlFile.content)
    uploadModel.value.tomlContent = tomlContent
    processUpdatedTomlContent(uploadModel, protocolData)
  }
}

/**
 * Processes and updates protocol data based on any modified TOML content
 *
 * @param uploadModel Reference to the upload model that contains updated TOML content
 * @param protocolData Reference to the protocol data that should be updated
 * @returns True if processing was successful, false otherwise
 */
export function processUpdatedTomlContent(
  uploadModel: Ref<UploadModel>,
  protocolData: Ref<ProtocolData | null>,
): boolean {
  try {
    // Get the current TOML content from the model
    const tomlContent = uploadModel.value.tomlContent

    if (!tomlContent || !protocolData.value) {
      return false
    }

    // Parse the TOML content to update metadata
    const parsedToml = parse(tomlContent)

    // Update the protocol data with the new TOML content
    protocolData.value.toml_config = tomlContent

    // Update metadata if present in the TOML
    if (parsedToml.airalogy_protocol && typeof parsedToml.airalogy_protocol === "object") {
      // Extract protocol data from parsed TOML
      const protocol = parsedToml.airalogy_protocol as Record<string, any>

      // Get the original metadata or initialize empty object if it doesn't exist
      const originalMetadata = protocolData.value.metadata.airalogy_protocol || {} as ProtocolMetaData

      // Update the metadata with parsed values, preserving existing values when new ones are not provided
      Object.assign(originalMetadata, {
        id: protocol.id || originalMetadata.id || "",
        version: protocol.version || originalMetadata.version || "",
        name: protocol.name || originalMetadata.name || "",
        license: protocol.license || originalMetadata.license || "",
        description: protocol.description || originalMetadata.description || "",
        authors: Array.isArray(protocol.authors) ? protocol.authors : originalMetadata.authors || [],
        maintainers: Array.isArray(protocol.maintainers) ? protocol.maintainers : originalMetadata.maintainers || [],
        disciplines: Array.isArray(protocol.disciplines) ? protocol.disciplines : originalMetadata.disciplines || [],
        keywords: Array.isArray(protocol.keywords) ? protocol.keywords : originalMetadata.keywords || [],
      })

      // Update the protocol data metadata
      protocolData.value.metadata.airalogy_protocol = originalMetadata

      // Update metadata in upload model if available
      const protocolMetadata = originalMetadata

      // Update metadata fields
      uploadModel.value.metadata = {
        ...uploadModel.value.metadata,
        id: protocolMetadata.id || "",
        name: protocolMetadata.name || "",
        version: protocolMetadata.version || "",
        authors: protocolMetadata.authors || [],
        maintainers: protocolMetadata.maintainers || [],
        description: protocolMetadata.description || "",
        disciplines: protocolMetadata.disciplines || [],
        keywords: protocolMetadata.keywords || [],
        license: protocolMetadata.license || "",
      }

      // Update version in root
      if (protocolMetadata.version) {
        uploadModel.value.version = protocolMetadata.version
      }

      // Update description if available
      if ("description" in protocolMetadata) {
        uploadModel.value.description = protocolMetadata.description as string
      }
    }

    return true
  }
  catch (error) {
    console.error("Error processing TOML content:", error)
    return false
  }
}

/**
 * Complete workflow for processing a protocol zip file including handling updated TOML content
 *
 * @param file The zip file to process
 * @param uploadModel Reference to the upload model
 * @param protocolData Reference to the protocol data
 * @param processZipFileFn Function to process the zip file
 * @returns Object containing success status and any error
 */
export async function processProtocolZipWorkflow(
  file: File,
  uploadModel: Ref<UploadModel>,
  protocolData: Ref<ProtocolData | null>,
  processZipFileFn: (file: File) => Promise<void>,
): Promise<{ success: boolean, error?: Error }> {
  try {
    // Process the zip file
    await processZipFileFn(file)

    // Process any updated TOML content
    if (uploadModel.value.tomlContent) {
      processUpdatedTomlContent(uploadModel, protocolData)
    }

    return { success: true }
  }
  catch (error) {
    console.error("Error processing protocol zip:", error)
    return {
      success: false,
      error: error instanceof Error ? error : new Error("Unknown error processing protocol zip"),
    }
  }
}

/**
 * Handles TOML content updates from the metadata form
 *
 * @param tomlContent New TOML content from the form
 * @param uploadModel Reference to the upload model
 * @param protocolData Reference to the protocol data
 * @returns Object with success status and any error
 */
export function handleTomlContentUpdate(
  tomlContent: string,
  uploadModel: Ref<UploadModel>,
  protocolData: Ref<ProtocolData | null>,
): { success: boolean, error?: Error } {
  try {
    // Update the TOML content in the model
    uploadModel.value.tomlContent = tomlContent

    // Process the updated TOML content
    const result = processUpdatedTomlContent(uploadModel, protocolData)

    if (!result) {
      return {
        success: false,
        error: new Error("Failed to process TOML content"),
      }
    }

    return { success: true }
  }
  catch (error) {
    console.error("Error updating TOML content:", error)
    return {
      success: false,
      error: error instanceof Error ? error : new Error("Unknown error updating TOML content"),
    }
  }
}

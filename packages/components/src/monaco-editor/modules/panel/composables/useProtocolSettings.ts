import type { ProtocolData } from "@airalogy/shared/constants"
import type { ProtocolMetaData } from "@airalogy/shared/types/models/protocol"
import type { FormInst } from "naive-ui"
import type { UploadModel } from "../../../types/upload"
import { useClosableMessage } from "@airalogy/composables"
import { DEFAULT_FILE_ID_MAP } from "@airalogy/shared/constants/protocol"
import { assert } from "@airalogy/shared/utils"
import { reactive, ref, watch } from "vue"
import { useUploadFileDataStore } from "../../../store/uploadFileDataStore"
import { processUpdatedTomlContent } from "../../../utils/protocolContentLoader"

export function useProtocolSettings() {
  // Store initialization
  const message = useClosableMessage()
  const uploadFileDataStore = useUploadFileDataStore()

  // TOML management
  const originalToml = ref("")
  const parseError = ref("")

  // Protocol form data
  const protocolForm = reactive<ProtocolMetaData>({
    id: "",
    version: "",
    // airalogy_protocol_id: "",
    name: "",
    authors: [],
    maintainers: [],
    disciplines: [],
    keywords: [],
    license: "",
    description: "",
  })
  // Get the generated TOML content
  const tomlContent = ref("")

  // Form reference
  const formRef = ref<FormInst | null>(null)

  // Load TOML content from the file
  async function loadTomlContent() {
    try {
      // Get the protocol.toml file from the uploadFileDataStore
      const tomlFile = uploadFileDataStore.getFileById(DEFAULT_FILE_ID_MAP.toml_config)

      if (tomlFile && tomlFile.content) {
        assert(typeof tomlFile.content === "string")
        originalToml.value = tomlFile.content
        tomlContent.value = tomlFile.content
        // Parse TOML and update form
        parseTomlToForm(tomlFile.content)
        console.log("Loaded protocol.toml content from store")
      }
      else {
        console.log("protocol.toml not found in store, creating default")
        // Create default TOML content based on the template

        originalToml.value = ""
        tomlContent.value = ""
      }
    }
    catch (error) {
      console.error("Error loading TOML content:", error)
      message.error("Failed to load protocol.toml content")
    }
  }

  // Parse TOML and update the form
  function parseTomlToForm(tomlString: string) {
    try {
      const uploadModel = ref<UploadModel>({
        tomlContent: tomlString,
      } as UploadModel)

      const protocolData = ref<ProtocolData | null>({
        metadata: {
          airalogy_protocol: protocolForm,
        },
      } as ProtocolData)

      const result = processUpdatedTomlContent(uploadModel, protocolData)

      if (result && protocolData.value?.metadata.airalogy_protocol) {
        Object.assign(protocolForm, protocolData.value.metadata.airalogy_protocol)
        parseError.value = ""
        return true
      }
      else {
        parseError.value = "Failed to parse TOML content."
        return false
      }
    }
    catch (error) {
      parseError.value = `TOML parse error: ${(error as Error).message}`
      console.error("TOML parse error:", error)
      return false
    }
  }

  async function syncTomlContentToStore(content: string, save = false) {
    if (!content) {
      return
    }

    const tomlFile = uploadFileDataStore.getFileById(DEFAULT_FILE_ID_MAP.toml_config)
    if (!tomlFile) {
      return
    }

    if (tomlFile.content === content && !save) {
      return
    }

    await uploadFileDataStore.updateFileItem(DEFAULT_FILE_ID_MAP.toml_config, { content }, save)
  }

  // Save changes to the file
  async function saveChanges() {
    try {
      const nextToml = tomlContent.value || originalToml.value

      // Update the original TOML reference
      originalToml.value = nextToml

      // Update the file data in the store
      try {
        await syncTomlContentToStore(nextToml, true)
        await nextTick()
        await loadTomlContent()
        message.success("Protocol saved successfully")
      }
      catch (error) {
        console.warn("Could not update file data in store:", error)
      }
    }
    catch (error) {
      console.error("Error saving TOML file:", error)
      message.error("Failed to save protocol.toml")
    }
  }

  // Reset changes to original content
  function resetChanges() {
    parseTomlToForm(originalToml.value)
    tomlContent.value = originalToml.value
    message.info("Changes reset to last saved version")
  }

  watch(tomlContent, (newToml) => {
    void syncTomlContentToStore(newToml)
  }, { flush: "sync" })

  return {
    protocolForm,
    originalToml,
    parseError,
    tomlContent,
    formRef,
    loadTomlContent,
    parseTomlToForm,
    saveChanges,
    resetChanges,
  }
}

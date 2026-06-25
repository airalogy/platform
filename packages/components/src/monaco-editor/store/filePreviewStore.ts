import type { FileInterface } from "../types"
import { defineStore } from "pinia"
import { ref } from "vue"

export const useFilePreviewStore = defineStore("file-preview", () => {
  const currentPreviewFile = ref<FileInterface | null>(null)
  const isPreviewMode = ref(false)

  function setPreviewFile(fileInfo: FileInterface | null) {
    currentPreviewFile.value = fileInfo
    isPreviewMode.value = !!fileInfo
  }

  function clearPreview() {
    currentPreviewFile.value = null
    isPreviewMode.value = false
  }

  function openFilePreview(fileInfo: FileInterface) {
    setPreviewFile(fileInfo)
  }

  return {
    currentPreviewFile,
    isPreviewMode,
    setPreviewFile,
    clearPreview,
    openFilePreview,
  }
})

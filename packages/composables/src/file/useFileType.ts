import type { Ref } from "vue"
import { FILE_TYPES, type ZipItem } from "@airalogy/shared/utils"

export function useFileType(selectedFile: Ref<ZipItem | null>) {
  const isTextFile = computed(() => {
    if (!selectedFile.value) {
      return false
    }

    return FILE_TYPES.text.some(ext => selectedFile.value!.name.toLowerCase().endsWith(ext))
  })

  const isImageFile = computed(() => {
    if (!selectedFile.value) {
      return false
    }

    return FILE_TYPES.image.some(ext => selectedFile.value!.name.toLowerCase().endsWith(ext))
  })

  const isProtocolFile = computed(() => {
    if (!selectedFile.value) {
      return false
    }

    return selectedFile.value.name.toLowerCase().endsWith(".aimd")
  })

  const isCsvFile = computed(() => {
    if (!selectedFile.value) {
      return false
    }

    return selectedFile.value.name.toLowerCase().endsWith(".csv")
  })

  return {
    isTextFile,
    isImageFile,
    isProtocolFile,
    isCsvFile,
  }
}

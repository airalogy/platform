import type { UploadSettledFileInfo } from "naive-ui"
import { normalizeAimdUploadFiles } from "@/utils/aimd-files"
import FilePreview from "@airalogy/components/file-preview/index.vue"
import { getBaseUploadProps, getFileInfo } from "@airalogy/shared"
import { h } from "vue"

export function getUploadProps(type: string, filePreviewProps?: Record<string, any>, extension?: string) {
  const baseProps = extension ? { accept: extension.startsWith(".") ? extension : `.${extension}` } : getBaseUploadProps(type)

  const renderIcon = (file: UploadSettledFileInfo) => {
    // Ensure file has proper name and type for FilePreview
    const uploadFile = normalizeAimdUploadFiles(file)[0]
    const fileName = uploadFile.name || `file.${type || "unknown"}`
    const fileInfo = getFileInfo(fileName)

    const normalizedFile = {
      ...uploadFile,
      name: fileName,
      // Use detected type from filename first, then fall back to provided type
      // Note: file.type is MIME type (e.g., "text/csv"), we need simple type (e.g., "csv")
      type: fileInfo.type !== "unknown" ? fileInfo.type : type,
    }

    return h(FilePreview, {
      class: "platform-aimd-file-preview",
      file: normalizedFile,
      ...(filePreviewProps || {}),
    })
  }

  return { ...baseProps, renderIcon }
}

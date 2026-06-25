import type { UploadSettledFileInfo } from "naive-ui"
import FilePreview from "@airalogy/components/file-preview/index.vue"
import { getBaseUploadProps, getFileInfo } from "@airalogy/shared"
import { h } from "vue"

export function getUploadProps(type: string, filePreviewProps?: Record<string, any>, extension?: string) {
  const baseProps = extension ? { accept: extension.startsWith(".") ? extension : `.${extension}` } : getBaseUploadProps(type)

  const renderIcon = (file: UploadSettledFileInfo) => {
    // Ensure file has proper name and type for FilePreview
    const fileName = file.name || `file.${type || "unknown"}`
    const fileInfo = getFileInfo(fileName)

    const normalizedFile = {
      ...file,
      name: fileName,
      // Use detected type from filename first, then fall back to provided type
      // Note: file.type is MIME type (e.g., "text/csv"), we need simple type (e.g., "csv")
      type: fileInfo.type !== "unknown" ? fileInfo.type : type,
    }

    return h(FilePreview, {
      file: normalizedFile,
      ...(filePreviewProps || {}),
    })
  }

  return { ...baseProps, renderIcon }
}

import type { UploadFileInfo, UploadInst } from "naive-ui"
import type { ComputedRef, Ref } from "vue"

export function useLogoUpload(
  logoValue: Ref<string | undefined>,
  logoUrlValue?: ComputedRef<string | undefined>,
) {
  const logoUploadRef = ref<{ uploadRef: UploadInst } | null>(null)
  const fileRef = ref<File | null>(null)

  const defaultFileList = computed(() => {
    if (!logoValue.value) {
      return []
    }

    return [{
      id: logoValue.value,
      name: logoValue.value,
      url: logoUrlValue?.value || logoValue.value,
      status: "finished",
    } as UploadFileInfo]
  })

  function handleSelectLogo(fileInfo: {
    file: UploadFileInfo
    fileList: UploadFileInfo[]
    event?: Event | undefined
  }) {
    const { file, status } = fileInfo.file

    if (status === "removed") {
      fileRef.value = null
      logoValue.value = undefined
      return
    }

    fileRef.value = file || null

    if (!logoUploadRef.value) {
      return
    }

    const { uploadRef } = logoUploadRef.value
    void nextTick(() => {
      uploadRef.submit()
    })
  }

  function handleUploadedLogo(fileInfo: Api.Attachment.AttachmentItem) {
    const { id } = fileInfo
    logoValue.value = id
  }

  return {
    logoUploadRef,
    fileRef,
    defaultFileList,
    handleSelectLogo,
    handleUploadedLogo,
  }
}

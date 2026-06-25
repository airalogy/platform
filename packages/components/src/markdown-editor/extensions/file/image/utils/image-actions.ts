import type { CustomImageOptions, ImageActionProps } from "../types"
import { base64MimeType, downloadAs, isBase64, isUrl } from "@airalogy/shared/utils"

// import { postAddAttachments } from "@airalogy/components/service/api/attachments"

function handleError(error: unknown, props: ImageActionProps, errorHandler?: (error: Error, props: ImageActionProps) => void): void {
  const typedError = error instanceof Error ? error : new Error("Unknown error")
  errorHandler?.(typedError, props)
}

export async function defaultDownloadImage(props: ImageActionProps, options: CustomImageOptions): Promise<void> {
  const { src, alt } = props
  const potentialName = alt || "image"

  try {
    if (isBase64(src)) {
      // For data URLs, extract the blob and mime type
      const mimeType = base64MimeType(src)
      const base64Data = src.split(",")[1]
      const byteCharacters = atob(base64Data)
      const byteArray = new Uint8Array(byteCharacters.length)
      for (let i = 0; i < byteCharacters.length; i++) {
        byteArray[i] = byteCharacters.charCodeAt(i)
      }
      const blob = new Blob([byteArray], { type: mimeType })
      const extension = mimeType.split(/\/|\+/)[1] || "png"

      downloadAs(blob, `${potentialName}.${extension}`, mimeType)
    }
    else if (isUrl(src, { requireHostname: false })) {
      // For regular URLs, fetch the content as blob
      const response = await fetch(src, {
        mode: "no-cors",
        referrerPolicy: "no-referrer",
      })
      if (!response.ok)
        throw new Error("Failed to fetch image")

      const blob = await response.blob()
      const extension = blob.type.split(/\/|\+/)[1] || "png"
      downloadAs(blob, `${potentialName}.${extension}`, blob.type)
    }

    options.onActionSuccess?.({ ...props, action: "download" })
  }
  catch (error) {
    handleError(error, { ...props, action: "download" }, options.onActionError)
  }
}

export async function defaultCopyImage(props: ImageActionProps, options: CustomImageOptions): Promise<void> {
  const { src } = props
  try {
    const res = await fetch(src)
    const blob = await res.blob()
    await navigator.clipboard.write([new ClipboardItem({ [blob.type]: blob })])
    options.onActionSuccess?.({ ...props, action: "copyImage" })
  }
  catch (error) {
    handleError(error, { ...props, action: "copyImage" }, options.onActionError)
  }
}

export async function defaultCopyLink(props: ImageActionProps, options: CustomImageOptions): Promise<void> {
  const { src } = props
  try {
    await navigator.clipboard.writeText(src)
    options.onActionSuccess?.({ ...props, action: "copyLink" })
  }
  catch (error) {
    handleError(error, { ...props, action: "copyLink" }, options.onActionError)
  }
}

export async function defaultCopyId(props: ImageActionProps, options: CustomImageOptions): Promise<void> {
  const { airalogyId } = props
  try {
    await navigator.clipboard.writeText(airalogyId || "")
    options.onActionSuccess?.({ ...props, action: "copyId" })
  }
  catch (error) {
    handleError(error, { ...props, action: "copyId" }, options.onActionError)
  }
}

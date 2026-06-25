import type { CustomFileOptions, DownloadFileCommandProps, UploadReturnType } from "../types"

export type ImageAction = "download" | "copyImage" | "copyLink" | "copyId"

export interface DownloadImageCommandProps extends DownloadFileCommandProps {
  action: ImageAction
}

export interface ImageActionProps extends DownloadImageCommandProps {
  airalogyId?: string
}

export interface CustomImageOptions extends CustomFileOptions {
  uploadFn?: (file: File, editor: Editor, options: CustomImageOptions) => Promise<UploadReturnType>
  onImageRemoved?: (props: Attrs) => void
  onActionError?: (error: Error, props: ImageActionProps) => void
  onActionSuccess?: (props: ImageActionProps) => void
  downloadImage?: (props: ImageActionProps, options: CustomImageOptions) => Promise<void>
  copyImage?: (props: ImageActionProps, options: CustomImageOptions) => Promise<void>
  copyLink?: (props: ImageActionProps, options: CustomImageOptions) => Promise<void>
  copyId?: (props: ImageActionProps, options: CustomImageOptions) => Promise<void>
}

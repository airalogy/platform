import type { FileValidationOptions } from "@airalogy/shared"
import type { Attrs } from "@tiptap/pm/model"
import type { Editor } from "@tiptap/vue-3"

export type FileAction = "download" | "copyLink" | "copyId"

export interface DownloadFileCommandProps {
  src: string
  id?: string
  alt?: string
}

export interface FileActionProps extends DownloadFileCommandProps {
  action: FileAction
  airalogyId?: string
}

export interface FileInfo {
  id?: string | number
  src: string
}

export type UploadReturnType =
  | null
  | string
  | {
    filename: string
    id: string | number
    airalogyId?: string
    src: string
  }

export interface FileUploadOptions extends FileValidationOptions {
  /**
   * Controls if the image node should be inline or not.
   * @default false
   * @example true
   */
  inline: boolean

  /**
   * HTML attributes to add to the image element.
   * @default {}
   * @example { class: 'foo' }
   */
  HTMLAttributes: Record<string, any>
  uploadFn?: (file: File, editor: Editor, options: CustomFileOptions) => Promise<UploadReturnType>
  onUploadError?: (error: Error) => void
  onUploadSuccess?: (response: any) => void
  protocolId?: string | null
  postAddAttachments?: (file: File, protocolId?: string | null) => Promise<any>
  resolveFile?: (id: string) => Promise<FileInfo | null>
}

interface CustomFileOptions extends FileUploadOptions, Omit<FileValidationOptions, "allowBase64"> {
  uploadFn?: (file: File, editor: Editor, options: CustomFileOptions) => Promise<UploadReturnType>
  onFileRemoved?: (props: Attrs) => void
  onActionSuccess?: (props: FileActionProps) => void
  onActionError?: (error: Error, props: FileActionProps) => void
  downloadFile?: (props: FileActionProps, options: CustomFileOptions) => Promise<void>
  copyLink?: (props: FileActionProps, options: CustomFileOptions) => Promise<void>
  copyId?: (props: FileActionProps, options: CustomFileOptions) => Promise<void>
  onValidationError?: (errors: FileError[]) => void
  onToggle?: (editor: Editor, files: File[], pos: number) => void
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    airalogyFile: {
      /**
       * Add an image
       */
      setFile: (options: { src: string, alt?: string, title?: string }) => ReturnType
      /**
       * Upload and add an image with placeholder
       */
      uploadFn: (file: File, protocolId?: string) => ReturnType
    }
  }
}

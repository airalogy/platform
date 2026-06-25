import type { ZipItem } from "@airalogy/shared"
import type { ProtocolMetaData } from "@airalogy/shared/types/models/protocol"
import type { UploadFileInfo } from "naive-ui"

export interface DirectoryFile {
  name: string
  path: string
  file: File
  size?: number
  lastModified?: number
}

export interface DirectoryUpload {
  type: "directory"
  files: DirectoryFile[]

  updated: boolean
}

export type UploadContent = DirectoryUpload | ZipUpload

export interface ZipUpload {
  type: "zip"
  content: {
    items: ZipItem[]
    root: string
  }
  updated: boolean
}

export interface UploadModel {
  fileList: UploadFileInfo[]
  file: File | null
  tomlContent: string | null
  envFileInclusion?: Record<string, boolean>
  metadata: ProtocolMetaData
  version: string
  description?: string
}

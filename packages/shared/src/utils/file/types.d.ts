import type { UnzipFileInfo } from "fflate"

export interface ZipItem extends UnzipFileInfo {
  path: string
  isDirectory: boolean
  content?: Uint8Array
  lastModified?: Date
}

export interface FileTypeMap {
  text: string[]
  image: string[]
}

export { UnzipFileInfo }

export interface DataNode {
  title: string
  key: string
  isLeaf?: boolean
  children?: DataNode[]
}

export interface EmptyFileInterface {
  name: string
  kind: "directory" | "file"
  path: string
  id: string
  status?: "pending" | "success" | "error"
  fileUrl?: string
  fileSize?: number
  fileType?: string
  isRemovable?: boolean
  isEditable?: boolean
  isSelectable?: boolean
}

export interface FileInterface extends EmptyFileInterface {
  content: string | Uint8Array<ArrayBufferLike>
}

export interface FilerInterface extends FileInterface {
  // handler?: FileSystemFileHandle
}

export interface DirectoryInterface extends EmptyFileInterface {
  children: Array<FileSystemItem>
}

export interface DirectorySuperInterface extends EmptyFileInterface {
  // handler: FileSystemDirectoryHandle
  children: Array<FileSystemSuperItem>
}

export type FileSystemItem = DirectoryInterface | FileInterface
export type FileSystemSuperItem = DirectorySuperInterface | FilerInterface

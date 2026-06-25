import type { DirectoryInterface, FileInterface, FileSystemItem } from "../types"
import { arrayBufferToString, FILE_TYPES, getFileType } from "@airalogy/shared"

async function saveFile(dirHandle: FileSystemDirectoryHandle, file: FileInterface) {
  const fileHandle = await dirHandle.getFileHandle(file.name, { create: true })
  const writable = await fileHandle.createWritable()
  await writable.write(file.content)
  await writable.close()
}

async function saveDirectory(dirHandle: FileSystemDirectoryHandle, directory: DirectoryInterface) {
  const newDirHandle = await dirHandle.getDirectoryHandle(directory.name, { create: true })
  for (const item of directory.children) {
    if (item.kind === "file") {
      await saveFile(newDirHandle, item as FileInterface)
    }
    else if (item.kind === "directory") {
      await saveDirectory(newDirHandle, item as DirectoryInterface)
    }
  }
}

async function loadFile(fileHandle: FileSystemFileHandle): Promise<FileInterface> {
  const file = await fileHandle.getFile()
  const buffer = await file.arrayBuffer()
  const content = new Uint8Array(buffer)
  const isTextFile = FILE_TYPES.text.some(ext => file.name.toLowerCase().endsWith(ext))

  return {
    id: file.name,
    name: file.name,
    kind: "file",
    path: fileHandle.name,
    content: isTextFile ? arrayBufferToString(content) : content,
    fileSize: file.size,
    fileType: getFileType(file.name),
    fileUrl: isTextFile ? undefined : URL.createObjectURL(file),
    children: [],
  } as unknown as FileInterface
}

async function loadDirectory(dirHandle: FileSystemDirectoryHandle): Promise<DirectoryInterface> {
  const children: FileSystemItem[] = []
  for await (const entry of dirHandle.values()) {
    if (entry.kind === "file") {
      children.push(await loadFile(entry as FileSystemFileHandle))
    }
    else if (entry.kind === "directory") {
      children.push(await loadDirectory(entry as FileSystemDirectoryHandle))
    }
  }
  return {
    id: dirHandle.name,
    name: dirHandle.name,
    kind: "directory",
    path: dirHandle.name,
    children,
  } as DirectoryInterface
}

export function useOPFS() {
  async function saveProject(projectId: string, files: FileSystemItem[]) {
    try {
      const root = await navigator.storage.getDirectory()
      const projectDirHandle = await root.getDirectoryHandle(projectId, { create: true })

      for (const item of files) {
        if (item.kind === "file") {
          await saveFile(projectDirHandle, item as FileInterface)
        }
        else if (item.kind === "directory") {
          await saveDirectory(projectDirHandle, item as DirectoryInterface)
        }
      }
    }
    catch (error) {
      console.error(`[useOPFS] Failed to save project ${projectId}:`, error)
      throw error
    }
  }

  async function loadProject(projectId: string): Promise<FileSystemItem[] | null> {
    try {
      const root = await navigator.storage.getDirectory()
      const projectDirHandle = await root.getDirectoryHandle(projectId)
      const items: FileSystemItem[] = []
      for await (const entry of projectDirHandle.values()) {
        if (entry.kind === "file") {
          items.push(await loadFile(entry as FileSystemFileHandle))
        }
        else if (entry.kind === "directory") {
          items.push(await loadDirectory(entry as FileSystemDirectoryHandle))
        }
      }
      return items
    }
    catch (error) {
      if (error instanceof DOMException && error.name === "NotFoundError") {
        return null
      }
      console.error(`[useOPFS] Failed to load project ${projectId}:`, error)
      throw error
    }
  }

  async function deleteProject(projectId: string) {
    try {
      const root = await navigator.storage.getDirectory()
      await root.removeEntry(projectId, { recursive: true })
    }
    catch (error) {
      console.error(`[useOPFS] Failed to delete project ${projectId}:`, error)
      throw error
    }
  }

  return {
    saveProject,
    loadProject,
    deleteProject,
  }
}

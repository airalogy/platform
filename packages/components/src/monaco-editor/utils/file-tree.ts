import type { DirectoryInterface, FileSystemItem } from "../types"
import { nanoid } from "nanoid"
import { isDirectory } from "./filesystem"

export function findById(items: FileSystemItem[], id: string): FileSystemItem | null {
  const _find = (currentItems: FileSystemItem[]): FileSystemItem | null => {
    for (const item of currentItems) {
      if (item.id === id) {
        return item
      }
      if (isDirectory(item) && item.children) {
        const found = _find(item.children)
        if (found) {
          return found
        }
      }
    }
    return null
  }
  return _find(items)
}

export function findByFilename(items: FileSystemItem[], filename: string): FileSystemItem | null {
  const _find = (currentItems: FileSystemItem[]): FileSystemItem | null => {
    for (const item of currentItems) {
      if (item.name === filename) {
        return item
      }
      if (isDirectory(item) && item.children) {
        const found = _find(item.children)
        if (found) {
          return found
        }
      }
    }
    return null
  }
  return _find(items)
}

export function findByPath(items: FileSystemItem[], path: string): FileSystemItem | null {
  const _find = (currentItems: FileSystemItem[]): FileSystemItem | null => {
    for (const item of currentItems) {
      if (item.path === path) {
        return item
      }
      if (isDirectory(item) && item.children) {
        const found = _find(item.children)
        if (found) {
          return found
        }
      }
    }
    return null
  }
  return _find(items)
}

export function findParent(items: FileSystemItem[], id: string, returnSelf = false): DirectoryInterface | null {
  const _findParent = (currentItems: FileSystemItem[], parent: DirectoryInterface | null): DirectoryInterface | null => {
    for (const item of currentItems) {
      if (item.id === id) {
        if (returnSelf && isDirectory(item)) {
          return item
        }

        return parent
      }
      if (isDirectory(item) && item.children) {
        const found = _findParent(item.children, item)
        if (found) {
          return found
        }
      }
    }
    return null
  }
  return _findParent(items, null)
}

export function removeItemById(items: FileSystemItem[], id: string): boolean {
  const _removeItem = (currentItems: FileSystemItem[]): boolean => {
    for (let i = 0; i < currentItems.length; i++) {
      const item = currentItems[i]
      if (item.id === id) {
        currentItems.splice(i, 1)
        return true
      }
      if (isDirectory(item) && item.children) {
        if (_removeItem(item.children)) {
          return true
        }
      }
    }
    return false
  }
  return _removeItem(items)
}

function isDuplicate(items: FileSystemItem[], name: string, type: "directory" | "file"): boolean {
  return items.some(item => item.name === name && item.kind === type)
}

export type AddItemPayload = (FileSystemItem) & { parent: DirectoryInterface | null, rootPath?: string }
export function addItem(
  items: FileSystemItem[],
  payload: AddItemPayload,
): void {
  const { kind, name, parent, status, id, rootPath = "", path } = payload
  const parentItem = parent || findParent(items, id)

  if (!parentItem || !isDirectory(parentItem)) {
    console.warn("Parent directory does not exist.")
    return
  }
  else if (parentItem.children && isDuplicate(parentItem.children, name, kind)) {
    console.warn(`Item with name "${name}" and type "${kind}" already exists.`)
    return
  }

  const newId = id || nanoid()
  const fallbackPath = `${rootPath}/${name}`

  let newEntry: FileSystemItem
  if (isDirectory(payload)) {
    newEntry = {
      id: newId,
      name,
      path: path || fallbackPath,
      kind: "directory",
      children: [],
      status,
      isRemovable: true,
      isEditable: true,
    }
  }
  else {
    newEntry = {
      id: newId,
      name,
      path: path || fallbackPath,
      kind: "file",
      content: "",
      status,
      isRemovable: true,
      isEditable: true,
    }
  }

  if (!parentItem.children) {
    parentItem.children = []
  }

  // newEntry.path = `${parentItem.path}/${newEntry.name}`
  parentItem.children.push(newEntry)
}

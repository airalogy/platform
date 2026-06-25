import type { FileInterface } from "."

export interface ProtocolDocument {
  id: string
  name: string
  size: number
  type: string
  content?: string
  status: "init" | "modified" | "uploaded" | "error" | "pending" | "success"
  createdAt: Date
  airalogyFileId?: string
  url?: string
  protocolId?: string | number
  metadata?: Record<string, any>
  modelId?: string // Track associated Monaco model ID
  path: string // Path where document is stored in the WebContainer file system
}
export interface ProtocolListItem extends ProtocolDocument {
  metadata: {
    isExist: boolean
    isUpdated: boolean
    source: string
    sourceFile: Omit<FileInterface, "content"> & { content: string } | null
    sourceId: string
    language: string
    [key: string]: any
  }
  content: string
  key: keyof GenOptions
}

export interface GenOptions {
  protocol: boolean
  model: boolean
  assigner: boolean
}

export interface GeneratedItems {
  protocol?: ProtocolListItem | null
  model?: ProtocolListItem | null
  assigner?: ProtocolListItem | null
}

// Comprehensive step configuration interface
export interface StepConfig {
  key: keyof GenOptions
  title: string
  description: string
  canGenerate: boolean
  generatedItem: any | undefined
}

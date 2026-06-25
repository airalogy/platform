import type { ChatModelConfig } from "@airalogy/shared"
import { request } from "../request"

export interface ExtractedProtocolInstructionFile {
  filename: string
  text: string
  was_trimmed: boolean
  content_type: string
}

export interface EditorCodeEditWorkspaceFile {
  path: string
  content: string
  type: "aimd" | "py" | "toml" | "other"
}

export interface EditorCodeEditSelection {
  text: string
  start_offset: number
  end_offset: number
}

export interface EditorCodeEditHistoryMessage {
  role: "user" | "assistant"
  content: string
}

export interface EditorCodeEditChangedFile {
  path: string
  name: string
  type: "aimd" | "py" | "toml"
  status: "created" | "modified" | "deleted"
  content: string
  diff: string
}

export interface EditorCodeEditResponse {
  runtime: "opencode"
  message: string
  edit_status: "changed" | "no_changes"
  changed_files: EditorCodeEditChangedFile[]
  warnings: string[]
  execution_log: string[]
}

export interface EditorCodeEditPayload {
  prompt: string
  workspace_id?: string
  files: EditorCodeEditWorkspaceFile[]
  active_file_path?: string
  selection?: EditorCodeEditSelection
  chat_history?: EditorCodeEditHistoryMessage[]
  model: ChatModelConfig
}

export async function extractProtocolInstructionFile(file: File) {
  if (!file) {
    throw new Error("file is required")
  }

  const formData = new FormData()
  formData.append("file", file)

  const { data, error } = await request<ExtractedProtocolInstructionFile>({
    url: "/editor/protocol_instruction_extract",
    method: "POST",
    data: formData,
    timeout: 1000 * 60 * 5,
  })

  return { data, error }
}

/**
 * Generate AIMD file based on user instruction
 * @param payload Request payload
 * @param payload.instruction User input instruction (1-20000 characters)
 * @param payload.model Chat model configuration
 * @returns Generated AIMD file content (plain text)
 */
export async function generateProtocolAimd(payload: {
  instruction: string
  model: ChatModelConfig
}, requestId?: string) {
  const { data, error } = await request<string>({
    url: "/editor/protocol_generate_aimd",
    method: "POST",
    data: payload,
    timeout: 1000 * 60 * 5, // 5 minutes timeout
    headers: {
      Accept: "text/plain",
    },
    metadata: {
      requestId,
    },
  })

  return { data, error }
}

/**
 * Generate Python model based on AIMD file
 * @param payload Request payload
 * @param payload.protocol_aimd AIMD file content (1-3000 characters)
 * @param payload.model Chat model configuration
 * @returns Generated Python model code (plain text)
 */
export async function generateProtocolModel(payload: {
  protocol_aimd: string
  model: ChatModelConfig
}, requestId?: string) {
  const { data, error } = await request<string>({
    url: "/editor/protocol_generate_model",
    method: "POST",
    data: payload,
    timeout: 1000 * 60 * 5,
    headers: {
      Accept: "text/plain",
    },
    metadata: {
      requestId,
    },
  })

  return { data, error }
}

/**
 * Generate Assigner based on AIMD and Model content
 * @param payload Request payload
 * @param payload.protocol_aimd AIMD file content (1-3000 characters)
 * @param payload.protocol_model Python model code (1-3000 characters)
 * @param payload.model Chat model configuration
 * @returns Generated Assigner code (plain text)
 */
export async function generateProtocolAssigner(payload: {
  protocol_aimd: string
  protocol_model: string
  model: ChatModelConfig
}, requestId?: string) {
  const { data, error } = await request<string>({
    url: "/editor/protocol_generate_assigner",
    method: "POST",
    data: payload,
    timeout: 1000 * 60 * 5,
    headers: {
      Accept: "text/plain",
    },
    metadata: {
      requestId,
    },
  })

  return { data, error }
}

export async function postEditorCodeEdit(payload: EditorCodeEditPayload, requestId?: string) {
  const { data, error } = await request<EditorCodeEditResponse>({
    url: "/editor/code_edit",
    method: "POST",
    data: payload,
    timeout: 1000 * 60 * 5,
    metadata: {
      requestId,
    },
  })

  return { data, error }
}

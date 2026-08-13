import type { CodeEditRequest, CodeEditResponse } from "@airalogy/masterbrain-client"
import type { ChatModelConfig } from "@airalogy/shared"
import { request } from "../request"

export interface ExtractedProtocolInstructionFile {
  filename: string
  text: string
  was_trimmed: boolean
  content_type: string
}

export interface EditorCodeEditPayload extends Omit<CodeEditRequest, "model"> {
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
  const { data, error } = await request<CodeEditResponse>({
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

import type { ProtocolModels } from "@airalogy/shared/types"
import { request } from "../request"

export async function getAttachments(id: string | number) {
  if (!id) {
    throw new Error("id is required")
  }

  return await request<Api.Attachment.AttachmentItem>({
    url: `/attachments/${id}`,
    method: "GET",
  })
}

export async function postUploadFile(protocolId: string, key: string, file: File) {
  if (!protocolId) {
    throw new Error("id is required")
  }
  if (!key) {
    throw new Error("key is required")
  }

  if (!file) {
    throw new Error("file is required")
  }

  const formData = new FormData()
  formData.append("file", file)

  const { data, error } = await request<Api.Attachment.AttachmentItem>({
    url: `/airalogy/upload/${protocolId}`,
    method: "POST",
    headers: {
      "airalogy-api-key": key,
    },
    data: formData,
    timeout: 60 * 1000 * 5,
  })

  if (error) {
    throw error
  }

  if (data) {
    return data
  }

  return null
}

export async function getDownloadFile(assetId: string, key: string) {
  if (!assetId) {
    throw new Error("id is required")
  }
  if (!key) {
    throw new Error("key is required")
  }

  return await request<Api.Attachment.AttachmentItem>({
    url: `/airalogy/download/${assetId}`,
    headers: {
      "airalogy-api-key": key,
    },
  })
}

export async function getRecordMetadata(rrecId: string, key: string) {
  if (!rrecId) {
    throw new Error("id is required")
  }
  if (!key) {
    throw new Error("key is required")
  }

  const { data, error } = await request<ProtocolModels.ProjectProtocolInfo>({
    url: `/airalogy/get_records/${rrecId}`,
    headers: {
      "airalogy-api-key": key,
    },
  })

  if (error) {
    throw error
  }

  if (data) {
    return data
  }

  return null
}

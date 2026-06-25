import { request } from "../request"

export async function fetchProtocolFolders(
  projectId: string,
  payload: { page?: number, pageSize?: number } = { page: 1, pageSize: 100 },
  requestId?: string,
) {
  const { page = 1, pageSize = 100 } = payload
  return await request<Api.GetResponseWithCount<"folders", Api.ProtocolFolder.Folder[]>>({
    url: `/projects/${projectId}/protocol_folders`,
    params: {
      page,
      page_size: pageSize,
    },
    metadata: {
      requestId,
    },
  })
}

export async function postProtocolFolder(
  projectId: string,
  payload: {
    name: string
    description?: string
  },
) {
  return await request<Api.ProtocolFolder.Folder>({
    url: `/projects/${projectId}/protocol_folders`,
    method: "POST",
    data: payload,
  })
}

export async function putProtocolFolder(
  projectId: string,
  folderId: number,
  payload: {
    name?: string
    description?: string
  },
) {
  return await request<Api.ProtocolFolder.Folder>({
    url: `/projects/${projectId}/protocol_folders/${folderId}`,
    method: "PUT",
    data: payload,
  })
}

export async function deleteProtocolFolder(projectId: string, folderId: number) {
  return await request<Api.ActionSuccessResponse>({
    url: `/projects/${projectId}/protocol_folders/${folderId}`,
    method: "DELETE",
  })
}

export async function putProtocolFolders(
  projectId: string,
  protocolId: string,
  folderIds: number[],
) {
  return await request<{ message: string, folder_ids: number[] }>({
    url: `/projects/${projectId}/protocols/${protocolId}/folders`,
    method: "PUT",
    data: {
      folder_ids: folderIds,
    },
  })
}

export async function putFolderProtocols(
  projectId: string,
  folderId: number,
  protocolIds: string[],
) {
  return await request<{ message: string, protocol_ids: string[] }>({
    url: `/projects/${projectId}/protocol_folders/${folderId}/protocols`,
    method: "PUT",
    data: {
      protocol_ids: protocolIds,
    },
  })
}

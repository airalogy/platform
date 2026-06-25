import { request } from "@/service/request"

export interface StarFolder {
  id: number
  user_id: string
  name: string
  is_default?: boolean
  created_at: string
  updated_at: string
}

export enum StarResourceType {
  Question = 1,
  Answer = 2,
  Protocol = 3,
}

export interface Star {
  id: number
  resourceType: StarResourceType
  resourceId: string
  folderIds: number[]
}
export interface StarResponse {
  id: number
  user_id: string
  resource_type: StarResourceType
  resource_id: string
  resource_summary: string
  lab_uid?: string | null
  project_uid?: string | null
  protocol_uid?: string | null
  question_id?: string | null
  created_at: string
  folder_ids: number[]
}

export interface StarUser {
  id: string
  name: string
  avatar_url: string | null
}

function toStarResponse(data: unknown): StarResponse | null {
  if (!data || typeof data !== "object") {
    return null
  }

  const payload = data as Partial<StarResponse> & { data?: unknown[] }
  if (
    typeof payload.id === "number"
    && typeof payload.resource_id === "string"
    && Array.isArray(payload.folder_ids)
  ) {
    return payload as StarResponse
  }

  if (Array.isArray(payload.data) && payload.data.length > 0) {
    return toStarResponse(payload.data[0])
  }

  return null
}

// Get all star folders
export async function getStarFolders() {
  const { data } = await request<Api.GetResponseWithCount<"folders", StarFolder[]>>({
    url: "/stars/folders",
    method: "GET",
  })
  if (data) {
    return data
  }

  return null
}

// Create a new star folder
export async function createStarFolder(name: string) {
  const { data } = await request<StarFolder>({
    url: "/stars/folders",
    method: "POST",
    data: { name },
  })
  if (data) {
    return data
  }

  return null
}

// Update a star folder
export async function updateStarFolder(folderId: number, name: string) {
  const { data } = await request<StarFolder>({
    url: `/stars/folders/${folderId}`,
    method: "PUT",
    data: { name },
  })
  if (data) {
    return data
  }

  return null
}

// Delete a star folder
export async function deleteStarFolder(folderId: number) {
  const { data } = await request<Api.ActionSuccessResponse>({
    url: `/stars/folders/${folderId}`,
    method: "DELETE",
  })
  if (data) {
    return data
  }

  return null
}

// Get stars with pagination
export async function getStars(params?: {
  folder_id?: number
  resource_type?: StarResourceType
  page?: number
  page_size?: number
}) {
  const { data } = await request<Api.GetResponseWithCount<"stars", StarResponse[]>>({
    url: "/stars",
    method: "GET",
    params,
  })
  if (data) {
    return data
  }

  return null
}

// Create a star
export async function createStar(payload: { type: StarResourceType, id: string, folderIdList?: number[] }) {
  const { type, id, folderIdList } = payload
  if (!type || !id) {
    throw new Error("type and id are required")
  }

  const { data } = await request<Api.GetResponse<StarResponse> | StarResponse>({
    url: "/stars",
    method: "POST",
    data: {
      resource_type: type,
      resource_id: id,
      folder_ids: folderIdList,
    },
  })

  return toStarResponse(data)
}

// Update a star
export async function updateStar(starId: number, folderIds: number[]) {
  const { data } = await request<Api.GetResponse<StarResponse> | StarResponse>({
    url: `/stars/${starId}`,
    method: "PUT",
    data: { folder_ids: folderIds },
  })

  return toStarResponse(data)
}

// Delete a star
export async function deleteStar(starId: number) {
  const { data } = await request<Api.ActionSuccessResponse>({
    url: `/stars/${starId}`,
    method: "DELETE",
  })

  return data
}

// Get star users
export async function getStarUsers(params: {
  resource_type: StarResourceType
  resource_id: string
  page?: number
  page_size?: number
}) {
  const { data } = await request<Api.GetResponseWithCount<"users", StarUser[]>>({
    url: "/stars/users",
    method: "GET",
    params,
  })
  if (data) {
    return data
  }

  return null
}

import type { ProjectRole, ProjectType } from "@/enum"
import { request } from "../request"

// export async function fetchProjectList(labId: string | number, payload: {
//   page: number
//   pageSize: number
// } = { page: 1, pageSize: 10 }): Promise<{
//   projects: Api.Project.MyProjectInfo[]
//   total_count: number
// } | null> {
//   if (!labId) {
//     return null
//   }

//   const { page, pageSize } = payload
//   try {
//     const { data, error } = await request<{
//       projects: Api.Project.MyProjectInfo[]
//       total_count: number
//     }>({
//       url: "/projects",
//       params: { lab_id: labId, page_size: pageSize, page },
//     })

//     return data
//   }
//   catch (e) {
//     // NOPE
//     return null
//   }
// }

export async function fetchProjectList(
  payload: Partial<{
    labUid: string
    labId: string
    parentProjectId: string
    rootOnly: boolean
    uid: string
    name: string
    permissionAction: "create_protocol"
    page: number
    pageSize: number
  }>,
  requestId?: string,
) {
  const { labUid, labId, parentProjectId, rootOnly, uid, name, permissionAction, page = 1, pageSize = 10 } = payload
  if (!(labUid || labId || uid || name || permissionAction)) {
    throw new Error("Required at least one of labUid, labId, uid, name, permissionAction")
  }

  const { data, error } = await request<Api.GetResponseWithCount<"projects", Api.Project.MyProjectInfo[]>>({
    url: "/projects",
    params: {
      lab_uid: labId ? undefined : labUid,
      lab_id: labId,
      parent_project_id: parentProjectId || undefined,
      root_only: rootOnly || undefined,
      uid: uid || undefined,
      name: name || undefined,
      permission_action: permissionAction || undefined,
      page,
      page_size: pageSize,
    },
    metadata: {
      requestId,
    },
  })

  if (data) {
    return data
  }
  if (error) {
    throw error
  }
  return null
}

export async function addProjectMember(payload: {
  projectId: string | number
  userId: string | number
  role: Api.Project.ProjectRole
}) {
  const { projectId, role, userId } = payload

  return await request({
    url: `/projects/${projectId}/users`,
    method: "POST",
    data: {
      user_id: userId,
      role,
    },
  })
}

export async function getProjectInfo(payload: { labUid: string, projectUid: string }) {
  const { labUid, projectUid } = payload
  if (!labUid || !projectUid) {
    throw new Error("labUid and projectUid are required")
  }

  const { data } = await request<Api.Project.MyProjectInfo>({
    url: "/projects/by_uid",
    params: { lab_uid: labUid, project_uid: projectUid },
  })

  if (data) {
    return data
  }

  return null
}

export async function getProjectInfoById(projectId: string | number) {
  if (!projectId) {
    throw new Error("projectId is required")
  }

  const { data, error } = await request<Api.Project.MyProjectInfo>({
    url: `/projects/${projectId}`,
  })

  if (data) {
    return data
  }
  if (error) {
    throw error
  }
  return null
}

export async function putProjectInfo(payload: Partial<{
  projectId: string | number
  name: string
  displayName: string
  description: string
  avatar: string
  type: ProjectType
  publicAccessRole: ProjectRole.RECORDER | ProjectRole.EXPLORER | ProjectRole.VIEWER
}>) {
  const { projectId, description, displayName, name, avatar, type, publicAccessRole } = payload
  if (!projectId) {
    throw new Error("projectId is required")
  }

  return await request({
    url: `/projects/${projectId}`,
    method: "PUT",
    data: {
      description,
      display_name: displayName,
      name,
      avatar,
      type,
      public_access_role: publicAccessRole,
    },
  })
}

export async function deleteProject(id: string | number) {
  if (!id) {
    throw new Error("projectId is required")
  }

  return await request({ url: `/projects/${id}`, method: "DELETE" })
}

export async function postNewProject(payload: {
  labId: string | number
  parentProjectId?: string
  copyMembers?: boolean
  uid: string
  type: 1 | 2
  displayName?: string
  description?: string
}) {
  const { labId, parentProjectId, copyMembers, uid, displayName, description, type } = payload
  if (!labId) {
    throw new Error("labId is required")
  }

  if (!uid || !displayName) {
    throw new Error("uid and displayName are required")
  }

  if (!type) {
    throw new Error("type is required")
  }

  return await request<Api.Project.MyProjectInfo>({
    url: "/projects",
    method: "POST",
    data: {
      lab_id: labId,
      parent_project_id: parentProjectId,
      copy_members: copyMembers,
      name: displayName,
      uid,
      description,
      type,
    },
  })
}

export async function fetchProjectMembers(id: string | number, payload: {
  page: number
  pageSize: number
} = { page: 1, pageSize: 10 }, requestId?: string) {
  if (!id) {
    throw new Error("projectId is required")
  }

  const { page, pageSize } = payload
  return await request<{ users: Api.Project.MemberListItem[], total_count: number }>({
    url: `/projects/${id}/users`,
    method: "GET",
    params: {
      page,
      page_size: pageSize,
    },
    metadata: {
      requestId,
    },
  })
}
export async function fetchProjectAllMembers(id: string | number, payload: {
  page: number
  pageSize: number
} = { page: 1, pageSize: 10 }) {
  if (!id) {
    throw new Error("projectId is required")
  }

  const { page, pageSize } = payload
  return await request<{ users: Api.Project.MemberListItem[], total_count: number }>({
    url: `/projects/${id}/all_users`,
    method: "GET",
    params: {
      page,
      page_size: pageSize,
    },
  })
}

export async function deleteProjectMember(projectId: string | number, userId: string | number) {
  if (!projectId) {
    throw new Error("projectId is required")
  }
  if (!userId) {
    throw new Error("userId is required")
  }

  const { data, error } = await request<{ message: string }>({
    url: `/projects/${projectId}/users/${userId}`,
    method: "DELETE",
  })

  if (error) {
    throw error
  }
  if (data) {
    const { message } = data
    if (message === "success") {
      return true
    }
  }

  return false
}

export async function putProjectMember(projectId: string | number, payload: {
  userId: string | number
  role: Api.Project.ProjectRole
}) {
  if (!projectId) {
    throw new Error("projectId is required")
  }

  const { role, userId } = payload

  return await request({
    url: `/projects/${projectId}/users/${userId}`,
    method: "PUT",
    data: {
      user_id: userId,
      role,
    },
  })
}

export async function checkProjectUid(payload: { uid: string, labUid: string }) {
  const { uid, labUid } = payload
  if (!uid) {
    throw new Error("project uid is required")
  }
  if (!labUid) {
    throw new Error("labUid is required")
  }

  const { data, error } = await request<{ result: boolean, message: string }>({
    url: "/projects/check_uid",
    params: { uid, lab_uid: labUid },
    metadata: {
      noRetry: true,
    },
  })

  if (error) {
    throw error
  }

  const { result, message } = data

  return { data: { valid: result, message } }
}

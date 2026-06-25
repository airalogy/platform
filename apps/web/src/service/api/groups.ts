import type { ProjectRole } from "@/enum"
import { request } from "../request"

export async function fetchGroupsInfo(groupId?: string | number): Promise<Api.Groups.GroupsInfo | null> {
  if (!groupId) {
    return null
  }

  const { data, error } = await request<{ data: Api.Groups.GroupsInfo }>({
    url: `/groups/${groupId}`,
  })

  if (data) {
    return data.data || null
  }
  else if (error) {
    throw error
  }

  return null
}

export async function fetchGroupsProjectList(groupId?: string | number, payload: {
  page: number
  pageSize: number
} = { page: 1, pageSize: 10 }, requestId?: string) {
  if (!groupId) {
    return null
  }

  const { page, pageSize } = payload
  const { data, error } = await request<{
    projects: Api.Project.MyProjectInfo[]
    total_count: number
  }>({
    url: `/groups/${groupId}/projects`,
    params: {
      page,
      page_size: pageSize,
    },
    metadata: {
      requestId,
    },
  })

  if (data) {
    return data || null
  }
  else if (error) {
    throw error
  }

  return null
}

export async function fetchGroupsMemberList(groupId: number | string, payload: {
  page: number
  pageSize: number
}, requestId?: string) {
  if (!groupId) {
    throw new Error("groupId is required")
  }

  const { page, pageSize } = payload
  try {
    const { data, error } = await request<{ users: Api.Groups.MemberListItem[] }>({
      url: `/groups/${groupId}/users`,
      method: "GET",
      params: {
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
    return null
  }
  catch (e) {
    return null
  }
}

export async function addGroupsMember(groupId: string | number, payload: {
  userId: string | number
  role: Api.Groups.GroupsRole
}) {
  if (!groupId) {
    throw new Error("groupId is required")
  }

  const { role, userId } = payload

  return await request({
    url: `/groups/${groupId}/users`,
    method: "POST",
    data: {
      user_id: userId,
      // role,
    },
  })
}

export async function putGroupsInfo(payload: Partial<{
  groupId: string | number
  name: string
  displayName: string
  description: string
  avatar: string
}>) {
  const { groupId, description, displayName, name, avatar } = payload
  if (!groupId) {
    throw new Error("groupId is required")
  }

  return await request({
    url: `/groups/groups/${groupId as string}`,
    method: "PUT",
    data: {
      description,
      display_name: displayName,
      name,
      avatar,
    },
  })
}

export async function getGroupsInfo(id: string | number) {
  if (!id) {
    throw new Error("groupId is required")
  }

  return await request<{ data: Api.Groups.MyGroupsInfo }>({
    url: `/groups/${id}`,
  })
}

export async function fetchGroupsList(payload: {
  labId?: string | number
  labUid?: string
  page: number
  pageSize: number
  type?: 1 | 2
} = { page: 1, pageSize: 10 }, requestId?: string) {
  const { labId, labUid } = payload
  if (!labId && !labUid) {
    throw new Error("labId or labUid is required")
  }

  const { page, pageSize, type } = payload

  const { data } = await request<Api.GetResponseWithCount<"groups", Api.Groups.MyGroupsInfo[]>>({
    url: "/groups",
    params: { lab_id: labId, lab_uid: labUid, page_size: pageSize, page, type },
    metadata: {
      requestId,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function postNewGroup(payload: {
  labId: string
  name: string
  uid: string
  memberIdList: string[]
  projectList: { project_id: string, role: Api.Project.ProjectRole }[]
  description?: string
  avatar?: string
}) {
  const { name, uid, description, memberIdList, labId, projectList } = payload
  if (!name || !uid || !memberIdList || !projectList) {
    throw new Error("name, uid, memberIdList, projectList are required")
  }

  return await request<Api.Groups.MyGroupsInfo>({
    url: "/groups",
    method: "POST",
    data: {
      name,
      description,
      uid,
      member_ids: memberIdList,
      projects: projectList,
      lab_id: labId,
    },
  })
}

export async function deleteGroup(id: string | number) {
  if (!id) {
    throw new Error("groupId is required")
  }

  const { data, error } = await request<{ message: string }>({
    url: `/groups/${id}`,
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

export async function deleteGroupsMember(groupId: string | number, userId: string | number) {
  if (!groupId) {
    throw new Error("groupId is required")
  }
  if (!userId) {
    throw new Error("userId is required")
  }

  const { data, error } = await request<{ message: string }>({
    url: `/groups/${groupId}/users/${userId}`,
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

export async function addGroupsProjects(groupId: string | number, payload: { project_id: string | number, role: ProjectRole }) {
  if (!groupId) {
    throw new Error("groupId is required")
  }

  const { project_id, role } = payload
  if (!project_id) {
    throw new Error("projectId is required")
  }

  return await request({
    url: `/groups/${groupId}/projects`,
    method: "POST",
    data: {
      project_id,
      role,
    },
  })
}
export async function deleteGroupsProjects(groupId: string | number, projectId: string | number) {
  if (!groupId) {
    throw new Error("groupId is required")
  }
  if (!projectId) {
    throw new Error("projectId is required")
  }

  return await request({
    url: `/groups/${groupId}/projects/${projectId}`,
    method: "DELETE",
  })
}
export async function putGroupsProjectRole(groupId: string | number, payload: {
  projectId: string
  role: Api.Groups.GroupsRole
}) {
  const { role, projectId } = payload
  if (!groupId || !role || !projectId) {
    throw new Error("missing params")
  }

  return await request<{ project_id: string, role: ProjectRole }>({
    url: `/groups/${groupId}/projects/${projectId}`,
    method: "PUT",
    data: {
      project_id: projectId,
      role,
    },
  })
}

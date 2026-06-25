import { request } from "../request"

interface LabRequestOptions {
  showError?: boolean
}

export async function fetchLabInfo(labId?: string | number): Promise<Api.Lab.LabInfo | null> {
  if (!labId) {
    return null
  }

  const { data, error } = await request<{ data: Api.Lab.LabInfo }>({
    url: `/labs/${labId}`,
  })

  if (data) {
    return data.data || null
  }
  else if (error) {
    throw error
  }

  return null
}

export async function fetchLabMemberList(
  labId: number | string,
  payload: {
    page: number
    pageSize: number
  },
  requestId?: string,
) {
  if (!labId) {
    throw new Error("labId is required")
  }

  const { page, pageSize } = payload
  try {
    const { data } = await request<Api.GetResponseWithCount<"users", Api.Lab.MemberListItem[]>>({
      url: `/labs/${labId}/users`,
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
  catch {
    return null
  }
}
export async function addLabMember(
  labId: string,
  payload: {
    userId: string
    role: Api.Lab.LabRole
    alias?: string
  },
) {
  if (!labId) {
    throw new Error("labId is required")
  }

  const { role, userId, alias } = payload

  return await request({
    url: `/labs/${labId}/users`,
    method: "POST",
    data: {
      user_id: userId,
      role,
      alias,
    },
  })
}

export async function putLabMember(
  labId: string | number,
  payload: {
    userId: string | number
    role: Api.Lab.LabRole
    alias?: string | null
  },
) {
  if (!labId) {
    throw new Error("labId is required")
  }

  const { role, userId, alias } = payload

  const data = {
    user_id: userId,
    role,
    ...(alias !== undefined ? { alias } : {}),
  }

  return await request({
    url: `/labs/${labId}/users/${userId}`,
    method: "PUT",
    data,
  })
}

export async function putLabInfo(
  labId: string | number,
  payload: Partial<{
    name: string
    displayName: string
    description: string
    logo: string
    type?: 1 | 2
  }>,
) {
  const { description, name, logo, type } = payload
  if (!labId) {
    throw new Error("labId is required")
  }

  return await request({
    url: `/labs/${labId}`,
    method: "PUT",
    data: {
      description,
      name,
      logo,
      type,
    },
  })
}

export async function getLabInfo(id: string | number) {
  if (!id) {
    throw new Error("labId is required")
  }

  return await request<{ data: Api.Lab.LabInfo }>({
    url: `/labs/${id}`,
  })
}

export async function fetchLabList(
  payload: {
    page: number
    pageSize: number
    type?: 1 | 2
  } = { page: 1, pageSize: 10 },
  requestId?: string,
) {
  const { page, pageSize, type } = payload

  return await request<Api.GetResponse<Api.Lab.LabInfo>>({
    url: "/labs",
    params: { page_size: pageSize, page, type },
    metadata: {
      requestId,
    },
  })
}

export async function postNewLab(payload: {
  name: string
  uid: string
  type?: 1 | 2
  members: { user_id: string, role: Api.Lab.LabRole, alias?: string }[]
  description?: string
  logo?: string
}) {
  const { name, uid, description, members, logo } = payload

  if (!name || !uid || !members) {
    throw new Error("name, displayName, members and type are required")
  }

  return await request<Api.Lab.LabInfo>({
    url: "/labs",
    method: "POST",
    data: {
      name,
      description,
      uid,
      members,
      logo,
    },
  })
}

export async function deleteLab(
  id: string | number,
  options?: LabRequestOptions,
) {
  if (!id) {
    throw new Error("labId is required")
  }

  const { data, error } = await request<{ message: string }>({
    url: `/labs/${id}`,
    method: "DELETE",
    metadata: {
      showError: options?.showError ?? true,
    },
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

export async function getLabForceDeletePreview(
  labId: string | number,
  options?: LabRequestOptions,
): Promise<Api.Lab.ForceDeletePreview> {
  if (!labId) {
    throw new Error("labId is required")
  }

  const { data, error } = await request<{ data: Api.Lab.ForceDeletePreview }>({
    url: `/labs/${labId}/force_delete_preview`,
    metadata: {
      showError: options?.showError ?? true,
    },
  })

  if (error) {
    throw error
  }
  if (data) {
    return data.data
  }

  throw new Error("Failed to load lab force delete preview")
}

export async function postLabForceDelete(
  labId: string | number,
  payload: {
    labUid: string
    confirmIrreversible: boolean
  },
  options?: LabRequestOptions,
): Promise<Api.Lab.ForceDeleteJob> {
  if (!labId) {
    throw new Error("labId is required")
  }

  const { data, error } = await request<{ data: Api.Lab.ForceDeleteJob }>({
    url: `/labs/${labId}/force_delete`,
    method: "POST",
    data: {
      lab_uid: payload.labUid,
      confirm_irreversible: payload.confirmIrreversible,
    },
    metadata: {
      showError: options?.showError ?? true,
    },
  })

  if (error) {
    throw error
  }
  if (data) {
    return data.data
  }

  throw new Error("Failed to start lab force delete")
}

export async function getLabForceDeleteJob(
  labId: string | number,
  jobId: number,
  options?: LabRequestOptions,
): Promise<Api.Lab.ForceDeleteJob> {
  if (!labId) {
    throw new Error("labId is required")
  }

  const { data, error } = await request<{ data: Api.Lab.ForceDeleteJob }>({
    url: `/labs/${labId}/force_delete_jobs/${jobId}`,
    metadata: {
      showError: options?.showError ?? true,
    },
  })

  if (error) {
    throw error
  }
  if (data) {
    return data.data
  }

  throw new Error("Failed to load lab force delete job")
}

export async function deleteLabMember(labId: string | number, userId: string | number) {
  if (!labId) {
    throw new Error("labId is required")
  }
  if (!userId) {
    throw new Error("userId is required")
  }

  const { data, error } = await request<{ message: string }>({
    url: `/labs/${labId}/users/${userId}`,
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

export async function getLabInfoByUid(uid: string) {
  if (!uid) {
    throw new Error("lab uid is required")
  }

  return await request<{ data: Api.Lab.LabInfo }>({
    url: `/labs/uid/${uid}`,
  })
}

export const memoizedGetLabInfo = useMemoize(fetchLabInfo)

export async function checkLabUid(uid: string) {
  if (!uid) {
    throw new Error("lab uid is required")
  }

  const { data, error } = await request<{ result: boolean, message: string }>({
    url: "/labs/check_uid",
    params: { uid },
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

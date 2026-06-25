import type { ProtocolModels } from "@airalogy/shared/types"
import { formatPydanticErrors } from "@airalogy/shared/utils/errorFormatter.js"
import { request } from "../request"

export async function fetchUserList(search: string) {
  const { data, error } = await request<Api.GetResponse<Api.Profile.User>>({
    url: "/users",
    // params: REG_EMAIL.test(val) ? { email: val } : { username: val },
    params: { name_or_email: search },
  })

  if (data) {
    return data
  }

  if (error) {
    throw error
  }

  return null
}

export async function fetchUserProjects(
  userId: string | number,
  payload: {
    name?: string
    uid?: string
    labUid?: string
    sortedBy?: string
    pageSize: number
    page: number
  } = { page: 1, pageSize: 10 },
  requestId?: string,
): Promise<{
  projects: Api.Project.MyProjectInfo[]
  total_count: number
} | null> {
  if (!userId) {
    throw new Error("userId is required")
  }

  const { page, pageSize, name, uid, labUid, sortedBy } = payload

  const { data, error } = await request<{
    projects: Api.Project.MyProjectInfo[]
    total_count: number
  }>({
    url: `/users/${userId}/projects`,
    params: {
      page,
      page_size: pageSize,
      name: name || undefined,
      uid: uid || undefined,
      lab_uid: labUid || undefined,
      sorted_by: sortedBy || undefined,
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

export async function fetchUserLabs(
  userId: string | number,
  payload: {
    pageSize: number
    page: number
    name?: string
    uid?: string
    sortedBy?: string
  } = { page: 1, pageSize: 10 },
  requestId?: string,
): Promise<{
  labs: Api.Lab.LabInfo[]
  total_count: number
} | null> {
  if (!userId) {
    throw new Error("userId is required")
  }

  const { page, pageSize, name, uid, sortedBy } = payload
  const { data, error } = await request<{
    labs: Api.Lab.LabInfo[]
    total_count: number
  }>({
    url: `/users/${userId}/labs`,
    params: { page, page_size: pageSize, name: name || undefined, uid: uid || undefined, sorted_by: sortedBy || undefined },
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

export async function fetchUserGroups(
  userId: string | number,
  payload: {
    name?: string
    uid?: string
    pageSize: number
    page: number
  } = { page: 1, pageSize: 999 },
): Promise<{ groups: Api.Groups.MyGroupsInfo[], total_count: number } | null> {
  if (!userId) {
    throw new Error("userId is required")
  }

  const { page, pageSize, name, uid } = payload
  const { data } = await request<{
    groups: Api.Groups.MyGroupsInfo[]
    total_count: number
  }>({
    url: `/users/${userId}/groups`,
    params: { page, page_size: pageSize, name: name || undefined, uid: uid || undefined },
  })

  if (data) {
    return data
  }

  return null
}

/**
 * Fetch a user's protocols
 * @param userId The user ID
 * @param payload Optional pagination and filtering parameters
 * @returns List of protocols associated with the user
 */
export async function fetchUserProtocols(
  userId: string | number,
  payload: {
    pageSize?: number
    page?: number
    name?: string
    uid?: string
    sortedBy?: string
  } = { page: 1, pageSize: 10 },
  requestId?: string,
) {
  if (!userId) {
    throw new Error("userId is required")
  }

  const { page = 1, pageSize = 10, name, uid, sortedBy } = payload
  const { data } = await request<Api.GetResponseWithCount<"protocols", ProtocolModels.ProjectProtocolInfo[]>>({
    url: `/users/${userId}/protocols`,
    params: {
      page,
      page_size: pageSize,
      name: name || undefined,
      uid: uid || undefined,
      sorted_by: sortedBy || undefined,
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

export async function fetchCurrentUserRecords() {
  return await request<Api.GetResponseWithCount<"records", Api.Record.RecordData[]>>({ url: "/users/records" })
}

export interface RecordDiaryItem extends ProtocolModels.RecordInfo {
  user: Pick<Api.Profile.User, "id" | "username" | "name" | "avatar" | "avatar_url">
  lab: Pick<Api.Lab.LabInfo, "id" | "uid" | "name">
  project: Pick<Api.Project.MyProjectInfo, "id" | "uid" | "name">
  protocol: Pick<ProtocolModels.ProjectProtocolInfo, "id" | "uid" | "name">
}

export interface RecordDiaryEventItem {
  airalogy_record_id: string
  record_id: string
  record_version: number
  metadata: Pick<
    ProtocolModels.RecordMetadata,
    | "airalogy_protocol_id"
    | "lab_id"
    | "project_id"
    | "protocol_id"
    | "protocol_version"
    | "record_current_version_submission_time"
    | "record_current_version_submission_user_id"
    | "record_num"
    | "sha1"
  > & {
    protocol_uuid: string
    record_current_version_submission_username: string
  }
  user: Pick<Api.Profile.User, "id" | "username" | "name">
  lab: Pick<Api.Lab.LabInfo, "id" | "uid" | "name">
  project: Pick<Api.Project.MyProjectInfo, "id" | "uid" | "name">
  protocol: Pick<ProtocolModels.ProjectProtocolInfo, "id" | "uid" | "name">
}

export type RecordDiarySubmitter = "all" | "me"

export interface RecordDiaryQueryPayload {
  page?: number
  pageSize?: number
  labUid?: string
  projectUid?: string
  dateFrom?: string
  dateTo?: string
  limit?: number
}

export interface AccessibleRecordDiaryQueryPayload extends RecordDiaryQueryPayload {
  submitter?: RecordDiarySubmitter
}

export interface RecordDiarySummaryItem {
  date: string
  count: number
}

export interface RecordDiaryEventsResponse {
  events: RecordDiaryEventItem[]
  truncated: boolean
  limit: number
}

function buildRecordDiaryParams(payload: AccessibleRecordDiaryQueryPayload) {
  const {
    page,
    pageSize,
    labUid,
    projectUid,
    dateFrom,
    dateTo,
    submitter,
    limit,
  } = payload

  return {
    page,
    page_size: pageSize,
    lab_uid: labUid || undefined,
    project_uid: projectUid || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    submitter,
    limit,
  }
}

export async function fetchUserRecordDiary(
  userId: string | number,
  payload: RecordDiaryQueryPayload = { page: 1, pageSize: 10 },
  requestId?: string,
) {
  if (!userId) {
    throw new Error("userId is required")
  }

  const { data } = await request<Api.GetResponseWithCount<"records", RecordDiaryItem[]>>({
    url: `/users/${userId}/records`,
    params: buildRecordDiaryParams(payload),
    metadata: {
      requestId,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function fetchAccessibleRecordDiary(
  payload: AccessibleRecordDiaryQueryPayload = { page: 1, pageSize: 10 },
  requestId?: string,
) {
  const { data } = await request<Api.GetResponseWithCount<"records", RecordDiaryItem[]>>({
    url: "/users/record_diary",
    params: buildRecordDiaryParams({ ...payload, submitter: payload.submitter || "all" }),
    metadata: {
      requestId,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function fetchUserRecordDiaryEvents(
  userId: string | number,
  payload: RecordDiaryQueryPayload = {},
  requestId?: string,
) {
  if (!userId) {
    throw new Error("userId is required")
  }

  const { data } = await request<RecordDiaryEventsResponse>({
    url: `/users/${userId}/records/events`,
    params: buildRecordDiaryParams(payload),
    metadata: {
      requestId,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function fetchAccessibleRecordDiaryEvents(
  payload: AccessibleRecordDiaryQueryPayload = {},
  requestId?: string,
) {
  const { data } = await request<RecordDiaryEventsResponse>({
    url: "/users/record_diary/events",
    params: buildRecordDiaryParams({ ...payload, submitter: payload.submitter || "all" }),
    metadata: {
      requestId,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function fetchUserRecordDiarySummary(
  userId: string | number,
  payload: RecordDiaryQueryPayload = {},
  requestId?: string,
) {
  if (!userId) {
    throw new Error("userId is required")
  }

  const { data } = await request<{ summary: RecordDiarySummaryItem[] }>({
    url: `/users/${userId}/records/summary`,
    params: buildRecordDiaryParams(payload),
    metadata: {
      requestId,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function fetchAccessibleRecordDiarySummary(
  payload: AccessibleRecordDiaryQueryPayload = {},
  requestId?: string,
) {
  const { data } = await request<{ summary: RecordDiarySummaryItem[] }>({
    url: "/users/record_diary/summary",
    params: buildRecordDiaryParams({ ...payload, submitter: payload.submitter || "all" }),
    metadata: {
      requestId,
    },
  })

  if (data) {
    return data
  }

  return null
}

/**
 * Get user information by ID
 * @param id The user ID
 * @returns User information
 */
export const getUserInfoById = useMemoize(async (id: string | number) => {
  if (!id) {
    throw new Error("id is required")
  }

  return await request<Api.Profile.User>({ url: `/users/${id}` })
})

export async function fetchUserInfo(payload: { username?: string, id?: string }, showError = true) {
  if (!payload.username && !payload.id) {
    throw new Error("username or id is required")
  }

  return await request<Api.Profile.User>({ url: "/users/query", params: payload, metadata: { showError } })
}

/**
 * Get user by username
 * @param username The username
 * @returns User information
 */
export const getUserByUsername = useMemoize(async (username: string) => {
  if (!username) {
    throw new Error("username is required")
  }

  const res = await request<Api.GetResponse<Api.Profile.User>>({
    method: "get",
    url: "/users",
    params: {
      username,
    },
  })

  if (res.data?.total_count === 1) {
    return res.data.data[0]
  }

  return null
})

/**
 * Get user information
 * @param payload Object containing username or id
 * @returns User information
 */
export const getUserInfo = useMemoize(async (payload: { username?: string, id?: string }) => {
  if (!payload.username && !payload.id) {
    throw new Error("username or id is required")
  }

  const res = await fetchUserInfo(payload)
  if (res?.data) {
    return res.data
  }

  return null
})

export async function checkUsernameDuplicate(uid: string) {
  if (!uid) {
    return { duplicated: false, message: "" }
  }

  try {
    const { data, error } = await request<{ result: boolean }>({
      url: "/check_user_uid",
      params: { uid },
      metadata: {
        noRetry: true,
      },
    })

    if (error) {
      throw error
    }

    if (data && data.result) {
      return { duplicated: false, message: "" }
    }

    return { duplicated: true, message: "Username is unavailable" }
  }
  catch (error: any) {
    // If API returns 400 with "User UID already exists", it means username is duplicate
    const errorDetail = error?.response?.data?.detail
    if (typeof errorDetail === "string") {
      return { duplicated: true, message: errorDetail }
    }

    if (typeof errorDetail === "object") {
      const formattedError = formatPydanticErrors(errorDetail)
      return { duplicated: true, message: formattedError }
    }

    // For transient request errors, do not block local form validation. The
    // signup endpoint still enforces username uniqueness.
    console.error("Error checking username duplicate:", error)
    return { duplicated: false, message: "Unable to check username availability" }
  }
}

export async function fetchUserQuestions(
  userId: string | number,
  payload: {
    pageSize?: number
    page?: number
    query?: string
  } = { page: 1, pageSize: 10 },
) {
  if (!userId) {
    throw new Error("userId is required")
  }

  const { page = 1, pageSize = 10, query } = payload
  const { data } = await request<Api.GetResponseWithCount<"questions", Api.Discussion.QuestionItem[]>>({
    url: `/users/${userId}/questions`,
    params: {
      page,
      page_size: pageSize,
      q: query,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function fetchUserAnswers(
  userId: string | number,
  payload: {
    pageSize?: number
    page?: number
    sortBy?: string
  } = { page: 1, pageSize: 10, sortBy: "upvotes" },
) {
  if (!userId) {
    throw new Error("userId is required")
  }

  const { page = 1, pageSize = 10, sortBy = "upvotes" } = payload
  const { data } = await request<Api.GetResponseWithCount<"answers", Api.Discussion.AnswerItem[]>>({
    url: `/users/${userId}/answers`,
    params: {
      page,
      page_size: pageSize,
      sort_by: sortBy,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function fetchUserStarred(
  userId: string | number,
  payload: {
    pageSize?: number
    page?: number
    resourceType?: number // Based on StarResourceType enum
  } = { page: 1, pageSize: 10 },
) {
  if (!userId) {
    throw new Error("userId is required")
  }

  const { page = 1, pageSize = 10, resourceType } = payload
  const { data } = await request<{
    labs: Api.Lab.LabInfo[]
    projects: Api.Project.MyProjectInfo[]
    protocols: ProtocolModels.ProjectProtocolInfo[]
    total_count: number
  }>({
    url: `/users/${userId}/stars`,
    params: {
      page,
      page_size: pageSize,
      resource_type: resourceType,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function setUserAlias(payload: { target_user_id: string, alias: string }) {
  return request({
    url: "/users/set_user_alias",
    method: "POST",
    data: payload,
  })
}

export async function getUsersWithAliases(payload: { user_ids: string[], lab_id?: string }) {
  return request<Api.Alias.UserAlias[]>({
    url: "/users/get_user_aliases",
    method: "POST",
    data: payload,
  })
}

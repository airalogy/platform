import type { ProtocolModels } from "@airalogy/shared/types"
import type { PydanticError } from "@airalogy/shared/utils"
import { getSchemaKey } from "@airalogy/shared/utils"
import { isObject as _isObject, mergeWith as _mergeWith } from "lodash-es"
import { request } from "../request"

type SchemaFieldResponseKey = Parameters<typeof getSchemaKey>[0]

export function transformFieldKeys<T extends Record<string, any>>(obj: Record<string, any>): T {
  return Object.fromEntries(
    Object.entries(obj).map(([k, v]) => {
      const schemaKey = getSchemaKey(k as SchemaFieldResponseKey)

      if (schemaKey) {
        return [schemaKey, v]
      }

      return [k, v]
    }) as [string, any],
  ) as T
}

export function schemaCustomizer(objValue: any, srcValue: any): any {
  if (_isObject(objValue)) {
    if (Object.hasOwn(objValue, "properties")) {
      return _mergeWith((objValue as { properties: any }).properties, srcValue, schemaCustomizer)
    }

    if (_isObject(srcValue) && !Array.isArray(srcValue)) {
      return _mergeWith(objValue, srcValue, schemaCustomizer)
    }

    ; (objValue as { value: any }).value = srcValue
  }

  return objValue
}

export function transformFields(data: ProtocolModels.ProjectProtocolInfo): ProtocolModels.ProjectProtocolInfo {
  const { fields: responseFields, json_schema: responseSchema } = data

  const fields = transformFieldKeys<ProtocolModels.Fields>(responseFields)

  const schema = transformFieldKeys(responseSchema)

  return {
    ...data,
    fields,
    json_schema: schema,
  } as unknown as ProtocolModels.ProjectProtocolInfo
}

/**
 * Interface for syntax check request
 */
export interface SyntaxCheckRequest {
  file_type: string
  file_content: string
}

/**
 * Interface for syntax check response
 */
export interface SyntaxCheckResponse {
  result: boolean
  message: string
  lineno: number
  offset: number
}

/**
 * Check the syntax of a file
 * @param payload The syntax check request
 * @returns The syntax check response
 */
export async function postEditorSyntaxCheck(payload: SyntaxCheckRequest) {
  if (!payload.file_type || !payload.file_content) {
    throw new Error("file_type and file_content are required")
  }

  const { data, error } = await request<SyntaxCheckResponse>({
    url: "/editor/syntax_check",
    method: "POST",
    data: payload,
  })

  return { data, error }
}

/**
 * Interface for protocol debug request
 */
export interface ProtocolDebugRequest {
  full_protocol: string
  suspect_protocol: string
}

/**
 * Interface for protocol debug response
 */
export interface ProtocolDebugResponse {
  issues: {
    location: string
    description: string
    severity: "error" | "warning" | "info"
    suggested_fix?: string
  }[]
  summary?: string
}

/**
 * Debug a protocol by comparing the full protocol with a suspect protocol
 * @param payload The protocol debug request
 * @returns The debug results
 */
export async function postEditorProtocolDebug(payload: ProtocolDebugRequest) {
  if (!payload.full_protocol || !payload.suspect_protocol) {
    throw new Error("full_protocol and suspect_protocol are required")
  }

  const { data, error } = await request<ProtocolDebugResponse>({
    url: "/editor/protocol_debug",
    method: "POST",
    data: payload,
  })

  return { data, error }
}

/**
 * Get the list of protocols
 * @param payload Optional parameters for filtering and pagination
 * @returns The list of protocols
 */
export async function getProtocols(
  payload: {
    page?: number
    pageSize?: number
    name?: string
    q?: string
    labUid?: string
    projectId?: string
    projectUid?: string
    uid?: string
  } = {},
) {
  const { page = 1, pageSize = 10, name, q, labUid, projectId, projectUid, uid } = payload

  const { data, error } = await request<Api.GetResponseWithCount<"data", ProtocolModels.ProtocolInfo[]>>({
    url: "/protocols",
    params: {
      page,
      page_size: pageSize,
      name,
      q,
      lab_uid: labUid,
      project_id: projectId,
      project_uid: projectUid,
      uid,
    },
  })

  return { data, error }
}

/**
 * Get protocol information by ID
 * @param id Protocol ID
 * @param version Optional version of the protocol
 * @param showError Whether to show error messages
 * @param requestId Optional request ID for tracking
 * @returns The protocol information
 */
export async function getProtocolInfo(
  id: string,
  version?: string,
  showError = true,
  requestId?: string,
) {
  if (!id) {
    throw new Error("protocol id is required")
  }

  const { data, error } = await request<ProtocolModels.ProjectProtocolInfo>({
    url: `/protocols/${id}`,
    params: {
      version,
    },
    metadata: {
      showError,
      requestId,
    },
  })

  if (data) {
    return {
      data: transformFields(data),
      error,
    }
  }

  return { data, error }
}

/**
 * Get protocol information by UID
 * @param payload Object containing lab, project, and protocol UIDs
 * @param showError Whether to show error messages
 * @returns The protocol information
 */
export async function getProtocolInfoByUid(
  payload: { labUid: string, projectUid: string, protocolUid: string, version?: string },
  showError = true,
) {
  const { labUid, projectUid, protocolUid, version } = payload

  if (!labUid || !projectUid || !protocolUid) {
    throw new Error("labUid, projectUid and protocolUid are required")
  }

  const { data, error } = await request<ProtocolModels.ProjectProtocolInfo>({
    url: "/protocols/by_uid",
    params: {
      lab_uid: labUid,
      project_uid: projectUid,
      protocol_uid: protocolUid,
      version,
    },
    metadata: {
      showError,
    },
  })

  if (data) {
    return {
      data: transformFields(data),
      error,
    }
  }

  return { data, error }
}

/**
 * Get protocol information by Airalogy ID
 * @param id Airalogy protocol ID
 * @param showError Whether to show error messages
 * @returns The protocol information
 */
export async function getProtocolInfoByAiralogyId(id: string, showError = true) {
  if (!id) {
    throw new Error("airalogyId is required")
  }

  const { data, error } = await request<ProtocolModels.ProjectProtocolInfo>({
    url: "/protocols/by_airalogy_id",
    params: {
      airalogy_protocol_id: id,
    },
    metadata: {
      showError,
    },
  })

  if (data) {
    return {
      data: transformFields(data),
      error,
    }
  }

  return { data, error }
}

/**
 * Update protocol information
 * @param protocolId Protocol ID
 * @param payload Update payload
 * @returns The result of the update operation
 */
export async function updateProtocol(
  protocolId: string,
  payload: Partial<{
    name: string
    description: string
    env_vars: string
    disciplines: string[]
    keywords: string[]
  }>,
) {
  if (!protocolId) {
    throw new Error("protocol id is required")
  }

  return await request({
    url: `/protocols/${protocolId}`,
    method: "PUT",
    data: payload,
  })
}

/**
 * Delete a protocol
 * @param id Protocol ID
 * @returns Whether the deletion was successful
 */
export async function deleteProtocol(id: string) {
  if (!id) {
    throw new Error("protocol id is required")
  }

  const { data, error } = await request({
    url: `/protocols/${id}`,
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

/**
 * Get protocol versions
 * @param protocolId Protocol ID
 * @param payload Pagination parameters
 * @returns List of protocol versions
 */
export async function getProtocolVersions(
  protocolId: string,
  payload: { page?: number, pageSize?: number } = { page: 1, pageSize: 10 },
) {
  if (!protocolId) {
    throw new Error("protocol id is required")
  }

  const { page = 1, pageSize = 10 } = payload

  const { data, error } = await request<Api.GetResponseWithCount<"versions", ProtocolModels.ProtocolVersion[]>>({
    url: `/protocols/${protocolId}/versions`,
    params: {
      page,
      page_size: pageSize,
    },
  })

  return { data, error }
}

/**
 * Get protocol environment variables
 * @param protocolId Protocol ID
 * @returns The environment variables
 */
export async function getProtocolEnvVars(protocolId: string) {
  if (!protocolId) {
    throw new Error("protocol id is required")
  }

  const { data, error } = await request<ProtocolModels.EnvVar>({
    url: `/protocols/${protocolId}/env_vars`,
  })

  return { data, error }
}

/**
 * Reuse a protocol in another project
 * @param payload Reuse parameters
 * @returns The result of the reuse operation
 */
export async function reuseProtocol(payload: {
  sourceProtocolId: string
  targetProjectId: string
  name?: string
  uid?: string
}) {
  const { sourceProtocolId, targetProjectId, name, uid } = payload

  if (!sourceProtocolId || !targetProjectId) {
    throw new Error("sourceProtocolId and targetProjectId are required")
  }

  const { data, error } = await request<ProtocolModels.ProtocolInfo>({
    url: `/protocols/${sourceProtocolId}/reuse`,
    method: "POST",
    data: {
      target_project_id: targetProjectId,
      name,
      uid,
    },
  })

  return { data, error }
}

export interface ProtocolReuseUser {
  id: string
  username: string
  name: string
}

export interface ProtocolReuseProject {
  id: string
  name: string
  uid: string
  type: number
}

export interface ProtocolReuseLab {
  id: string
  name: string
  uid: string
}

export interface ProtocolReuseEntry {
  id: string
  uid: string
  name: string
  project_id: string
  created_at: string
  airalogy_id?: string
  parent_protocol_id: string
  parent_protocol_version: string | null
  project: ProtocolReuseProject
  lab: ProtocolReuseLab
  user: ProtocolReuseUser
}

/**
 * Get protocol reuse list
 * @param payload Optional pagination params
 * @returns Reuse list and total count
 */
export async function getProtocolReuses(payload: {
  protocolId: string
  page?: number
  pageSize?: number
}) {
  const { protocolId, page = 1, pageSize = 10 } = payload

  if (!protocolId) {
    throw new Error("protocol id is required")
  }

  const { data, error } = await request<Api.GetResponseWithCount<"protocols", ProtocolReuseEntry[]>>({
    url: `/protocols/${protocolId}/reuses`,
    method: "GET",
    params: {
      page,
      page_size: pageSize,
    },
  })

  return { data, error }
}

/**
 * Download protocol package
 * @param id Protocol ID
 * @param version Optional version
 * @returns The package content
 */
export async function getDownloadPackage(id: string, version?: string) {
  if (!id) {
    throw new Error("protocol id is required")
  }

  const { data, error } = await request({
    url: `/protocols/${id}/download_package`,
    params: {
      version,
    },
    responseType: "blob" as any,
  })

  return { data, error }
}

/**
 * Get package files for a protocol
 * @param id Protocol ID
 * @param version Optional version
 * @returns List of files in the package
 */
export async function getPackageFiles(id: string, version?: string) {
  if (!id) {
    throw new Error("protocol id is required")
  }

  const { data, error } = await request<string[]>({
    url: `/protocols/${id}/package_files`,
    params: {
      version,
    },
  })

  return { data, error }
}

// Record-related endpoints for protocols

type ValidateRecordData = Record<
  // Protocol.FieldKey,
  "research_variable" | "research_step" | "research_check" | "research_result",
  Record<
    string,
    string | number | boolean | { annotation: string, checked: boolean | null } | undefined
  >
>

interface ValidateRecordResult {
  data: Record<
    string,
    string | number | boolean | { annotation: string, checked: boolean | null } | undefined
  >
  errors: PydanticError[]
}

/**
 * Validate a record for a protocol
 * @param protocolId Protocol ID
 * @param payload Record data to validate
 * @returns Validation result
 */
export async function validateProtocolRecord(
  protocolId: string,
  payload: Record<string, any>,
) {
  if (!protocolId) {
    throw new Error("protocolId is required")
  }

  const { data, error } = await request<Partial<ValidateRecordResult>>({
    url: `/protocols/${protocolId}/records/validate`,
    method: "POST",
    data: {
      var: payload,
    },
  })

  if (data) {
    const { data: varData, errors } = data
    return {
      data: {
        research_variable: varData,
      } satisfies Partial<ValidateRecordData>,
      error: errors,
    }
  }

  return { data: null, error }
}

/**
 * Get protocol version history
 * @param id Protocol ID
 * @returns The history of protocol versions
 */
export async function getProtocolHistory(payload: { id: string, page?: number, pageSize?: number }) {
  const { id, page = 1, pageSize = 10 } = payload

  if (!id) {
    throw new Error("id is required")
  }

  const { data } = await request<Api.GetResponseWithCount<"versions", ProtocolModels.ProtocolVersion[]>>({
    url: `/protocols/${id}/versions`,
    params: {
      protocol_id: id,
      page,
      page_size: pageSize,
    },
  })

  if (data) {
    return data
  }

  return null
}

/**
 * Check if a protocol ID and version combination is valid
 * @param payload Object containing id and version
 * @returns Whether the ID and version are valid
 */
export async function postCheckProtocolIdDuplicate(payload: { uid: string, version?: string, labUid: string, projectUid: string }) {
  const { uid, version, labUid, projectUid } = payload
  if (!uid || !labUid || !projectUid) {
    throw new Error("uid, labUid and projectUid are required")
  }

  if (version && !/\d+\.\d+\.\d+$/.test(version)) {
    throw new Error("version must be in the format of [major].[minor].[patch]")
  }

  return await request<{ valid?: boolean, message?: string, suggested_version?: string }>({
    url: "/protocols/check_uid",
    method: "GET",
    params: {
      uid,
      version: version || undefined,
      lab_uid: labUid,
      project_uid: projectUid,
    },
    metadata: {
      showError: false,
      noRetry: true,
    },
  })
}

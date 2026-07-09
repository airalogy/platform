import type { FieldResponseKey } from "@airalogy/shared"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { AttachmentModels } from "@airalogy/shared/types/models"
import type { PydanticError } from "@airalogy/shared/utils/errorFormatter.js"
import { getSchemaKey } from "@airalogy/shared/utils"
import { isObject as _isObject, mergeWith as _mergeWith } from "lodash-es"
import { request } from "../request"

export function transformFieldKeys<T extends Record<string, any>>(obj: Record<string, any>): T {
  return Object.fromEntries(
    Object.entries(obj).map(([k, v]) => {
      const schemaKey = getSchemaKey(k as FieldResponseKey)

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

    if (Object.hasOwn(srcValue, "airalogy_file_id")) {
      ;(objValue as { value: any }).value = srcValue.airalogy_file_id
    }
    else if (_isObject(srcValue) && !Array.isArray(srcValue)) {
      return _mergeWith(objValue, srcValue, schemaCustomizer)
    }

    ;(objValue as { value: any }).value = srcValue
  }

  return objValue
}

export function transformFields(
  data: ProtocolModels.ProjectProtocolInfo,
): ProtocolModels.ProjectProtocolInfo {
  const { fields: responseFields, json_schema: responseSchema } = data

  const fields = transformFieldKeys<ProtocolModels.Fields>(responseFields)

  const schema = transformFieldKeys(responseSchema)

  return {
    ...data,
    fields,
    json_schema: schema,
  } as unknown as ProtocolModels.ProjectProtocolInfo
}

export async function getProtocolInfoByUid(
  payload: { labUid: string, projectUid: string, protocolUid: string, version?: string },
  showError = true,
) {
  const { labUid, projectUid, protocolUid, version } = payload
  if (!labUid || !projectUid || !protocolUid) {
    throw new Error("labUid, projectUid and uid are required")
  }

  const { data, error } = await await request<ProtocolModels.ProjectProtocolInfo>({
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

export async function getProtocolInfo(
  id: string | number,
  version?: string,
  showError = true,
  requestId?: string,
) {
  if (!id) {
    throw new Error("protocol id is required")
  }

  const { data, error } = await request<ProtocolModels.ProjectProtocolInfo>({
    url: `/protocols/${id}`,
    method: "GET",
    params: {
      version: version || undefined,
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

export async function deleteProtocol(id: string | number) {
  if (!id) {
    throw new Error("unit id is required")
  }

  const { data, error } = await request({ url: `/protocols/${id}`, method: "DELETE" })

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

export async function putProtocolInfo(
  protocolId: string | number,
  payload: Partial<{
    name: string
    description: string
    env: string
    uid: string
    disciplines: string[]
    keywords: string[]
    license: string
  }>,
) {
  if (!protocolId) {
    throw new Error("unit id is required")
  }

  const { name, env, uid, description, disciplines, keywords, license } = payload

  return await request({
    url: `/protocols/${protocolId}`,
    method: "PUT",
    data: {
      name,
      env_vars: env,
      uid,
      description,
      disciplines,
      keywords,
      // type,
      // members: null,
      license,
    },
  })
}

interface PostProtocolResponse {
  id: string
  project_id: string
  project_uid: string
  user_id: string
  uid: string
  name: string
  current_node_id: string | null
  created_at: string
  updated_at: string
  forks_count: number
  parent_research_id: string | null
  origin_researchnode_id: string | null
}

// export async function postNewProtocol(payload: {
//   uid: string
//   displayName: string
//   projectUUID: string
// }) {
//   const { displayName, uid, projectUUID } = payload
//   if (!uid || !projectUUID) {
//     throw new Error("name and projectUUID are required")
//   }

//   return await request<PostProtocolResponse>({
//     url: "/protocols",
//     method: "POST",
//     data: {
//       name: displayName,
//       uid,
//       project_id: projectUUID,
//     },
//   })
// }

type IValidateRecordData = Record<
  // Protocol.FieldKey,
  "research_variable" | "research_step" | "research_check" | "research_result",
  Record<
    string,
    string | number | boolean | { annotation: string, checked: boolean | null } | undefined
  >
>

interface IValidateRecordResult {
  data: Record<
    string,
    string | number | boolean | { annotation: string, checked: boolean | null } | undefined
  >
  errors: PydanticError[]
}

export async function postValidateRecord(protocolId: string, payload: Record<string, any>) {
  if (!protocolId) {
    throw new Error("protocolId is required")
  }

  const { data, error } = await request<Partial<IValidateRecordResult>>({
    url: `/protocols/${protocolId}/records/validate`,
    method: "POST",
    data: {
      var: payload,
    },
  })

  if (data) {
    // const { research_variable, research_check, research_result, research_step, errors } = data
    const { data: varData, errors } = data
    return {
      data: {
        research_variable: varData,
      } satisfies Partial<IValidateRecordData>,
      error: errors,
    }
  }

  return { data: null, error }
}

/**
 * Get download package URL (legacy, returns OSS URL)
 * Note: OpenAPI schema may show JSON response, but this is for getting the URL
 */
export async function getDownloadPackage(id: string, version: string) {
  if (!id) {
    throw new Error("id is required")
  }

  return await request<{ url: string }>({
    url: `/protocols/${id}/download_package`,
    method: "GET",
    params: {
      version,
    },
  })
}

/**
 * Download protocol package directly from backend as binary blob
 * This is the actual implementation - the API returns binary zip file directly
 * (OpenAPI schema description may be inaccurate, showing application/json)
 */
export async function getDownloadPackageDataDirect(id: string, version: string) {
  if (!id) {
    throw new Error("id is required")
  }

  const { data } = await request<Blob, "blob">({
    url: `/protocols/${id}/download_package`,
    method: "GET",
    params: {
      version,
    },
    responseType: "blob",
  })

  return data
}

/**
 * Download from OSS URL
 * Uses proxy in development to avoid CORS issues
 */
export async function getDownloadPackageData(url: string) {
  // In development, proxy configured object-storage requests to avoid CORS
  const isDev = import.meta.env.DEV
  const ossProxyTarget = import.meta.env.VITE_OSS_PROXY_TARGET?.replace(/\/$/, "")
  const isProxyableObjectStorageUrl = Boolean(ossProxyTarget) && url.startsWith(ossProxyTarget!)

  if (isDev && ossProxyTarget && isProxyableObjectStorageUrl) {
    // Convert object-storage URL to use local proxy
    // Use absolute URL (starting with http) to bypass axios baseURL
    const ossPath = url.slice(ossProxyTarget.length)
    const proxyUrl = `${window.location.origin}/oss-proxy${ossPath}`

    const { data } = await request({
      url: proxyUrl,
      method: "GET",
      responseType: "blob",
    })
    return data
  }

  // In production or non-OSS URLs, use original URL
  const { data } = await request({
    url,
    method: "GET",
    responseType: "blob",
  })

  return data
}

// export async function fetchProtocolByUid(payload: {
//   labUid: string
//   projectUid: string
//   page: number
//   pageSize: number
//   includeRecords?: boolean
// }) {
//   const { labUid, projectUid, page = 1, pageSize = 10, includeRecords } = payload
//   if (!labUid || !projectUid) {
//     throw new Error("labUid and projectUid are required")
//   }

//   return await request<{ researches: ProtocolInfo[], total_count: number }>({
//     url: "/protocols/by_uid",
//     params: {
//       lab_uid: labUid,
//       project_uid: projectUid,
//       page,
//       page_size: pageSize,
//       include_records: includeRecords,
//     },
//   })
// }

export async function fetchProtocols(
  payload: {
    page: number
    pageSize: number
    labUid?: string
    projectId?: string | number
    projectUid?: string
    name?: string
    uid?: string
    search_by?: string
    search_str?: string
    sorted_by?: string
    folderId?: number
    folderEmpty?: boolean
  } = { page: 1, pageSize: 10 },
  requestId?: string,
) {
  const {
    page,
    pageSize,
    labUid,
    projectUid,
    projectId,
    name,
    uid,
    search_by,
    search_str,
    sorted_by,
    folderId,
    folderEmpty,
  } = payload

  if (projectUid && !labUid) {
    throw new Error("labUid is required when projectUid is provided")
  }

  return await request<Api.GetResponseWithCount<"protocols", ProtocolModels.ProjectProtocolInfo[]>>(
    {
      url: "/protocols",
      params: {
        project_id: projectId,
        page,
        page_size: pageSize,
        lab_uid: labUid,
        project_uid: projectUid,
        name: name || undefined,
        uid: uid || undefined,
        search_by: search_by || undefined,
        search_str: search_str || undefined,
        sorted_by: sorted_by || undefined,
        folder_id: folderId || undefined,
        folder_empty: folderEmpty || undefined,
      },
      metadata: {
        requestId,
      },
    },
  )
}

export async function fetchProtocolRecords(
  protocolId: string | number,
  payload: {
    page: number
    pageSize: number
    protocolVersion?: string
    number?: number
    version?: string
    userId?: string
    q?: string
  } = { page: 1, pageSize: 10 },
) {
  if (!protocolId) {
    throw new Error("protocolId is required")
  }

  const { page, pageSize, protocolVersion, number, version, userId, q } = payload
  return await request<Api.GetResponseWithCount<"records", ProtocolModels.RecordInfo[]>>({
    url: `/protocols/${protocolId}/records`,
    method: "GET",
    params: {
      page,
      page_size: pageSize,
      protocol_version: protocolVersion || undefined,
      number: number || undefined,
      version: version || undefined,
      user_id: userId || undefined,
      q: q || undefined,
    },
  })
}

export async function postNewResearchRecord(
  protocolId: string,
  payload: Partial<
    Record<
      /* Protocol.FieldKey */
      "research_variable" | "research_step" | "research_check" | "research_result",
      Record<string, string | number | boolean | undefined>
    >
  > & {
    report?: string
  },
) {
  if (!protocolId) {
    throw new Error("protocolId is required")
  }

  const { research_check, research_step, research_variable, report } = payload
  return await request({
    url: `/protocols/${protocolId}/records`,
    method: "POST",
    data: {
      check: research_check || {},
      step: research_step || {},
      var: research_variable || {},
      report: "",
    },
  })
}

export interface ImportProtocolRecordsResponse {
  imported_count: number
  record_ids: string[]
  files?: Array<{
    id: string
    airalogy_file_id: string
    filename: string
    record_id: string
    record_version: number
  }>
}

export interface ImportAiraArchiveProtocolResult {
  archive_root: string
  id: string
  uid: string
  name: string
  project_id: string
  project_uid: string
  lab_id: string
  lab_uid: string
  protocol_version_id: string
  version: string
  created_protocol: boolean
  created_version: boolean
  reused_version: boolean
}

export interface ImportAiraArchiveResponse {
  kind: "protocol" | "protocols" | "records"
  protocols: ImportAiraArchiveProtocolResult[]
  records: Array<{
    id: string
    version: number
    protocol_id: string
    protocol_uid: string
    protocol_version: string
    number: number
  }>
  files: Array<{
    id: string
    airalogy_file_id: string
    filename: string
    record_id: string
    record_version: number
  }>
  imported_protocol_count: number
  imported_record_count: number
  imported_file_count: number
}

export async function postImportProtocolRecords(
  protocolId: string,
  payload: {
    file: File
    inputFormat?: "auto" | "csv" | "tsv" | "json" | "jsonl" | "aira"
  },
) {
  if (!protocolId) {
    throw new Error("protocolId is required")
  }
  if (!payload.file) {
    throw new Error("file is required")
  }

  const formData = new FormData()
  formData.append("file", payload.file)
  formData.append("input_format", payload.inputFormat || "auto")

  const { data, error } = await request<ImportProtocolRecordsResponse>({
    url: `/protocols/${protocolId}/records/import`,
    method: "POST",
    data: formData,
    timeout: 60 * 1000 * 5,
    metadata: {
      showError: false,
      errorClosable: false,
    },
  })

  if (error) {
    throw error
  }

  if (!data) {
    throw new Error("No import result returned")
  }

  return data
}

export async function postImportAiraArchive(projectId: string, payload: { file: File }) {
  if (!projectId) {
    throw new Error("projectId is required")
  }
  if (!payload.file) {
    throw new Error("file is required")
  }

  const formData = new FormData()
  formData.append("file", payload.file)

  const { data, error } = await request<ImportAiraArchiveResponse>({
    url: `/projects/${projectId}/aira/import`,
    method: "POST",
    data: formData,
    timeout: 60 * 1000 * 5,
    metadata: {
      showError: false,
      errorClosable: false,
    },
  })

  if (error) {
    throw error
  }

  if (!data) {
    throw new Error("No import result returned")
  }

  return data
}

export async function putUpdateResearchRecord(
  protocolId: string,
  recordId: string,
  payload: Partial<
    Record<
      /* Protocol.FieldKey */
      "research_variable" | "research_step" | "research_check" | "research_result",
      Record<string, string | number | boolean | undefined>
    >
  > & {
    report?: string
  },
) {
  if (!protocolId) {
    throw new Error("protocolId is required")
  }
  if (!recordId) {
    throw new Error("recordId is required")
  }

  const { research_check, research_step, research_variable } = payload
  return await request({
    url: `/protocols/${protocolId}/records/${recordId}`,
    method: "PUT",
    data: {
      check: research_check || {},
      step: research_step || {},
      var: research_variable || {},
      report: "",
    },
  })
}
export async function deleteResearchRecord(protocolId: string, recordId: string, version: number) {
  if (!protocolId) {
    throw new Error("protocolId is required")
  }
  if (!recordId) {
    throw new Error("recordId is required")
  }
  return await request({
    url: `/protocols/${protocolId}/records/${recordId}`,
    method: "DELETE",
    params: {
      version,
    },
  })
}

export async function postGetRvAssign(
  id: string | number,
  payload: { name: string, dependencies: Record<string, any> },
  requestId?: string,
) {
  if (!id) {
    throw new Error("id is required")
  }

  const { name, dependencies } = payload

  const { data, error } = await request<ProtocolModels.RvAssignerItem>({
    url: `/protocols/${id}/records/var_assign`,
    method: "POST",
    data: {
      var_name: name,
      dependent_data: dependencies,
    },
    metadata: {
      requestId,
      showError: false,
    },
    timeout: 60 * 1000 * 5,
  })

  if (error) {
    throw error
  }

  if (!data) {
    throw new Error("data is required")
  }

  const { success, assigned_fields, error_message } = data
  if (success) {
    return assigned_fields
  }

  if (error_message) {
    throw new Error(error_message)
  }

  return null
}

export async function getStaticResearchAssets(id: string | number, filename: string) {
  if (!id) {
    throw new Error("id is required")
  }
  if (!filename) {
    throw new Error("filename is required")
  }

  const response = await request<AttachmentModels.AttachmentItemResponse>({
    url: `/protocols/${id}/package_files`,
    method: "GET",
    params: {
      filename,
    },
  })

  return response
}

export async function postUploadReferenceAssets(id: string | number, payload: { file: File }) {
  if (!id) {
    throw new Error("id is required")
  }
  if (!payload.file) {
    throw new Error("file is required")
  }
  const formData = new FormData()
  formData.append("file", payload.file)
  formData.append("protocol_id", id.toString())

  const response = await request<Api.Attachment.AttachmentItem>({
    url: "/airalogy_files",
    method: "POST",
    data: formData,
  })

  return response
}

export async function getReferenceAssets(id: string | number, showError = true) {
  if (!id) {
    throw new Error("id is required")
  }

  const response = await request<Api.Attachment.AttachmentItem>({
    url: `/airalogy_files/${id}`,
    method: "GET",
    metadata: {
      showError,
    },
  })

  return response
}

export async function getResearchEnvVariables(id: string | number) {
  if (!id) {
    throw new Error("id is required")
  }

  const response = await request<{ env_vars: string | null }>({
    url: `/protocols/${id}/env_vars`,
    method: "GET",
  })

  return response
}

export async function putRenameAssets(id: string | number, filename: string) {
  if (!id) {
    throw new Error("id is required")
  }
  if (!filename) {
    throw new Error("filename is required")
  }

  const response = await request({
    url: `/airalogy_files/${id}/rename`,
    method: "PUT",
    data: {
      filename,
    },
  })

  return response
}

/**
 * Creates a new research by forking an existing research.
 *
 * @param {object} info - The payload containing the fork research details.
 * @param {string} info.parent_protocol_id - The ID of the research to fork.
 * @param {string} info.project_id - The ID of the project to associate the new research with.
 * @param {string} info.name - The name of the new research.
 * @param {string} info.uid - The unique identifier of the new research.
 * @return {ForkedProtocolResponse} The response containing the newly created research details.
 */
export async function postForkProtocol(payload: ProtocolModels.ForkProtocolRequestPayload) {
  const { parentProtocolId, protocolName, projectId, protocolUid } = payload

  const { data, error } = await request<ProtocolModels.ForkedProtocolResponse>({
    url: `/protocols/${parentProtocolId}/fork`,
    method: "POST",
    data: {
      name: protocolName,
      uid: protocolUid,
      project_id: projectId,
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

export async function postReuseProtocol(payload: {
  sourceProtocolId: string
  targetProjectUUID: string
  name: string
  uid: string
}) {
  const { sourceProtocolId, targetProjectUUID, name, uid } = payload

  const { data, error } = await request<ProtocolModels.ProjectProtocolInfo>({
    url: `/protocols/${sourceProtocolId}/reuse`,
    method: "POST",
    data: {
      target_project_id: targetProjectUUID,
      name,
      uid,
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

// export async function checkProtocolUid(payload: {
//   uid: string
//   labUid: string
//   projectUid: string
// }) {
//   const { uid, labUid, projectUid } = payload
//   if (!uid) {
//     throw new Error("unit uid is required")
//   }

//   return await request<{ valid: boolean, message: string }>({
//     url: "/protocols/check_uid",
//     params: { uid, lab_uid: labUid, project_uid: projectUid },
//     metadata: {
//       noRetry: true,
//     },
//   })
// }

export async function getProtocolRecordReport(payload: {
  recordId: string | number
  protocolId: string | number
  version?: string
}) {
  const { recordId, protocolId, version = 1 } = payload

  if (!recordId || !protocolId) {
    throw new Error("recordId and protocolId are required")
  }

  const { data, error } = await request<ProtocolModels.RecordInfo>({
    url: `/protocols/${protocolId}/records/${recordId}`,
    method: "GET",
    params: {
      version,
    },
  })

  if (error) {
    throw error
  }

  return data
}

export async function postUploadProtocol(payload: {
  file: File
  version?: string
  projectId: string
  protocolId?: string
  env?: string
}) {
  const { file, projectId, protocolId, env } = payload
  const form = new FormData()
  form.append("file", file)
  // form.append("version", version)
  form.append("project_id", projectId)
  if (protocolId) {
    form.append("protocol_id", protocolId)
  }

  if (env) {
    form.append("env_vars", env)
  }

  const { data, error } = await request<{ data: ProtocolModels.ForkedProtocolResponse }>({
    url: "/protocols",
    method: "POST",
    data: form,
    timeout: 60 * 1000 * 5,
    metadata: {
      errorClosable: false,
    },
  })

  if (data) {
    return data
  }

  return null
}

export async function postStarProtocol(payload: { projectId: string, protocolId: string }) {
  const { projectId, protocolId } = payload
  if (!projectId || !protocolId) {
    throw new Error("projectId and protocolId are required")
  }

  const res = await request<{ success: boolean }>({
    url: "/protocols/star",
    method: "POST",
    data: {
      project_id: projectId,
      protocol_id: protocolId,
    },
  })

  return res
}

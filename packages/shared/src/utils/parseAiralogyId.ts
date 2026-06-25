import type { ProtocolModels } from "../types"
import type { ProjectProtocolInfo } from "../types/models/protocol"

type IAiralogyIdType = "rn" | "file" | "qa" | "chat" | "lab" | "project" | "protocol"

type IAiralogyIdTarget = "model" | "record" | "protocol"

export interface IAiralogyIdBaseItem {
  lab: string
  project: string
  node: string
  version: {
    main: string
    minor: string
    patch: string
  }
}

export interface IAiralogyIdFileItem {
  type: "file"
  uuid: string
  extension: string
}

export interface IAiralogyIdModelItem extends IAiralogyIdBaseItem {
  type: "rn"
  target: "model"
  schema?: boolean | string
}

export interface IAiralogyIdRecordItem extends IAiralogyIdBaseItem {
  type: "rn"
  target: "record"
  record: { num: string, version: string }
}

export interface IAiralogyIdProtocolItem extends IAiralogyIdBaseItem {
  type: "rn"
  target: "protocol"
  record: { num: string, version: string }
}

export interface IAiralogyProtocolPathItem extends IAiralogyIdBaseItem {
  type: "protocol"
}

export type IAiralogyIdItem =
  | IAiralogyIdModelItem
  | IAiralogyIdRecordItem
  | IAiralogyIdProtocolItem
  | IAiralogyProtocolPathItem
  | IAiralogyIdFileItem

// Type predicates for type narrowing
export function isModelItem(item: IAiralogyIdItem): item is IAiralogyIdModelItem {
  return item.type === "rn" && item.target === "model"
}

export function isRecordItem(item: IAiralogyIdItem): item is IAiralogyIdRecordItem {
  return item.type === "rn" && item.target === "record"
}

export function isFileItem(item: IAiralogyIdItem): item is IAiralogyIdFileItem {
  return item.type === "file"
}

const typeRecord: Record<IAiralogyIdType, boolean> = {
  file: true,
  chat: true,
  qa: true,
  rn: true,
  lab: true,
  project: true,
  protocol: true,
}

export const AIRALOGY_ID_PREFIX = "airalogy.id."
export const AIRALOGY_FILE_ID_PREFIX = "airalogy.id.file."
export function parseAiralogyId(id: string): IAiralogyIdItem | IAiralogyIdFileItem | null {
  // TODO: Error
  if (!id) {
    return null
  }

  if (!id.startsWith(AIRALOGY_ID_PREFIX)) {
    return null
  }

  const items = id.slice(AIRALOGY_ID_PREFIX.length).split(".") as [IAiralogyIdType, ...string[]]

  const [type, ...info] = items

  if (!typeRecord[type]) {
    return null
  }

  if (type === "file") {
    const [uuid, extension] = info
    const result: IAiralogyIdFileItem = { uuid, extension, type: "file" }

    return result
  }

  if (type === "rn") {
    if (items.length < 6 || items.some(it => !it)) {
      return null
    }

    const [lab, project, node, main, minor, patch, ...rest] = info
    const base = {
      type: "rn" as const,
      lab,
      project,
      node,
      version: { main, minor, patch },
    }

    if (rest.length === 0) {
      return null
    }

    const target = rest[0] as IAiralogyIdTarget

    if (target === "record") {
      const [_, num, version] = rest
      const result: IAiralogyIdRecordItem = {
        ...base,
        target,
        record: { num, version },
      }

      return result
    }
    else if (target === "model") {
      const [_, schema, variable] = rest

      const result: IAiralogyIdModelItem = {
        ...base,
        target,
        schema: variable || (schema ? true : undefined),
      }

      return result
    }

    return null
  }

  if (type === "lab") {
    const [lab, projectLabel, project, protocolLabel, node, versionLabel, main, minor, patch] = info

    if (
      !lab
      || projectLabel !== "project"
      || !project
      || protocolLabel !== "protocol"
      || !node
      || versionLabel !== "v"
      || !main
      || !minor
      || !patch
    ) {
      return null
    }

    return {
      type: "protocol",
      lab,
      project,
      node,
      version: { main, minor, patch },
    }
  }

  return null
}

export function getAiralogyId(node: ProjectProtocolInfo | null) {
  if (!node) {
    return null
  }

  const { uid, lab, project, airalogy_id } = node

  if (airalogy_id) {
    return airalogy_id
  }

  return `${AIRALOGY_ID_PREFIX}${lab.uid}.${project.uid}.${uid}`
}

export function getRecordAiralogyId(node: ProjectProtocolInfo) {
  if (!node) {
    return null
  }

  const { uid, lab, project } = node

  return `${AIRALOGY_ID_PREFIX}${lab.uid}.${project.uid}.${uid}`
}

export function getAiralogyFileId(id: string, type: string) {
  if (!id) {
    return null
  }

  return `${AIRALOGY_FILE_ID_PREFIX}${id}.${type}`
}

export function getAiralogyIds(node: ProjectProtocolInfo) {
  if (!node) {
    return null
  }
  const { lab, project, uid, latest_version, metadata: { version } = {} } = node

  const labId = `${AIRALOGY_ID_PREFIX}lab.${lab.uid}`
  const projectId = `${labId}.project.${project.uid}`
  const protocolId = `${projectId}.protocol.${uid}.v.${version || latest_version}`

  return {
    lab: labId,
    project: projectId,
    protocol: protocolId,
  }
}

export function getProtocolId(payload: { labUid: string, projectUid: string, protocolUid: string, protocolVersion: string }) {
  const { labUid, projectUid, protocolUid, protocolVersion } = payload

  return `${AIRALOGY_ID_PREFIX}lab.${labUid}.project.${projectUid}.protocol.${protocolUid}.v.${protocolVersion}`
}

export function getNextRecommendedVersion(version: string, type: "major" | "minor" | "patch" = "patch") {
  const [major, minor, patch] = version.split(".").map(Number)
  if (type === "major") {
    return [major + 1, 0, 0].join(".")
  }
  else if (type === "minor") {
    return [major, minor + 1, 0].join(".")
  }
  return [major, minor, patch + 1].join(".")
}

export function getRealAiralogyId(protocol: ProtocolModels.ProjectProtocolInfo) {
  const { latest_version, metadata: { version } = {}, airalogy_id } = protocol
  if (!version || (version === latest_version && airalogy_id.endsWith(latest_version))) {
    return airalogy_id
  }

  return airalogy_id.replace(new RegExp(`${latest_version}$`), version)
}

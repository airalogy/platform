import { request } from "../request"

export type CompatibilityClassification
  = | "compatible"
  | "conditional"
  | "breaking"
  | "unknown"

export interface CompatibilityChange {
  path: string
  kind?: string
  message?: string
  classification?: CompatibilityClassification
  [key: string]: unknown
}

export interface CompatibilityReport {
  status: CompatibilityClassification
  recommended_bump: "patch" | "minor" | "major"
  actual_bump: "patch" | "minor" | "major"
  semver_valid: boolean
  changes: CompatibilityChange[]
}

export interface ProtocolVersionGovernance {
  protocol_id: string
  target_version: string
  compatibility_report: CompatibilityReport | null
  migration_manifest: Array<Record<string, unknown>> | Record<string, unknown> | null
  affected_records: number
  affected_resource_type_revisions: number
}

export interface GovernanceIssue {
  path?: string
  message: string
  migration?: string
}

export interface MigrationStep {
  from: string
  to: string
  status: string
  rule_hash: string
}

export interface RecordMigrationPreview {
  source_version: string
  target_version: string
  original_data: Record<string, unknown>
  data: Record<string, unknown>
  status: string
  issues: GovernanceIssue[]
  schema_issues: GovernanceIssue[]
  not_collected: string[]
  requires_sandbox: boolean
  rule_hash: string
  steps: MigrationStep[]
}

export interface RecordProjection {
  id: string
  record_id: string
  record_version: number
  source_protocol_version: string
  target_protocol_version: string
  rule_hash: string
  status: string
  projected_data: Record<string, unknown>
  not_collected: string[]
  issues: GovernanceIssue[]
  created_at: string
  updated_at: string
}

export interface MigratedRecord {
  id: string
  version: number
  protocol_version: string
  revision_kind: string
  revision_reason: string
  data: Record<string, unknown>
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (data === null)
    throw new Error("Schema governance returned no data")
  return data
}

function recordGovernanceUrl(protocolId: string, recordId: string, path: string) {
  return `/protocols/${protocolId}/records/${recordId}/${path}`
}

export function fetchProtocolVersionGovernance(protocolId: string, version: string) {
  return getData<ProtocolVersionGovernance>({
    url: `/protocols/${protocolId}/governance/versions/${version}`,
  })
}

export function previewRecordMigration(
  protocolId: string,
  recordId: string,
  targetVersion: string,
) {
  return getData<RecordMigrationPreview>({
    url: recordGovernanceUrl(protocolId, recordId, "migration-preview"),
    method: "POST",
    data: { target_version: targetVersion },
  })
}

export function migrateRecordSchema(
  protocolId: string,
  recordId: string,
  payload: {
    target_version: string
    reason: string
    idempotency_key: string
  },
) {
  return getData<{
    migration: Record<string, unknown>
    record: MigratedRecord
  }>({
    url: recordGovernanceUrl(protocolId, recordId, "migrations"),
    method: "POST",
    data: {
      ...payload,
      confirmed: true,
    },
  })
}

export function projectRecordSchema(
  protocolId: string,
  recordId: string,
  targetVersion: string,
) {
  return getData<RecordProjection>({
    url: recordGovernanceUrl(protocolId, recordId, "projections"),
    method: "POST",
    data: { target_version: targetVersion },
  })
}

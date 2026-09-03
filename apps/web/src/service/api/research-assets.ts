import { request } from "../request"

export type DataAssetKind = "file" | "table" | "image" | "model" | "archive" | "external"
export type DataAssetStatus = "draft" | "ready" | "superseded" | "archived"
export type EvidenceKind = "observation" | "measurement" | "analysis" | "citation" | "validation"
export type EvidenceQuality = "pending" | "validated" | "rejected"
export type ClaimState = "suggested" | "draft" | "reviewed" | "rejected" | "superseded" | "archived"
export type ClaimEvidenceRelation = "supports" | "contradicts" | "context"
export type EvidenceArtifactType = "record" | "data_asset" | "knowledge" | "paper_library_entry" | "external"
export type ResearchKnowledgeKind = "note" | "method" | "decision" | "finding"
export type ProtocolImprovementState = "suggested" | "reviewed" | "rejected" | "applied"

export interface DataAssetVersion {
  id: string
  data_asset_id: string
  version: number
  research_file_id?: string | null
  external_uri: string
  media_type: string
  checksum: string
  byte_size?: number | null
  data_schema: Record<string, unknown>
  version_metadata: Record<string, unknown>
  source: Record<string, unknown>
  change_summary: string
  created_by_user_id: string
  created_at: string
}

export interface DataAsset {
  id: string
  lab_id: string
  project_id: string
  task_id?: string | null
  name: string
  description: string
  kind: DataAssetKind
  status: DataAssetStatus
  current_version: number
  created_by_user_id: string
  created_at: string
  updated_at: string
  versions: DataAssetVersion[]
}

export interface ResearchEvidence {
  id: string
  task_id: string
  run_id?: string | null
  action_id?: string | null
  kind: EvidenceKind
  artifact_type: EvidenceArtifactType
  artifact_id: string
  artifact_version: string
  summary: string
  quality_state: EvidenceQuality
  validation_report: Record<string, unknown>
  created_by_user_id: string
  reviewed_by_user_id?: string | null
  reviewed_at?: string | null
  created_at: string
}

export interface ClaimEvidenceLink {
  id?: string
  claim_id?: string
  evidence_id: string
  relation: ClaimEvidenceRelation
  rationale: string
}

export interface ResearchClaim {
  id: string
  task_id: string
  statement: string
  state: ClaimState
  confidence?: number | null
  uncertainty: string
  generated_by: "human" | "aira_assisted"
  generation_id?: string | null
  generation_model?: string | null
  generation_snapshot?: AiraClaimGeneration | null
  generation_receipt_digest?: string | null
  revision: number
  created_by_user_id: string
  reviewed_by_user_id?: string | null
  reviewed_at?: string | null
  created_at: string
  updated_at: string
  evidence: ClaimEvidenceLink[]
}

export interface ResearchKnowledgeItem {
  id: string
  lab_id: string
  project_id: string
  visibility: "project"
  kind: ResearchKnowledgeKind
  state: "suggested" | "draft" | "reviewed" | "superseded" | "archived"
  title: string
  body: string
  tags: string[]
  revision: number
  generated_by: "human" | "aira"
  evidence: Array<{
    evidence_id: string
    source_snapshot: Record<string, unknown>
  }>
  created_at: string
  updated_at: string
}

export interface ProtocolImprovementProposal {
  id: string
  task_id: string
  protocol_id: string
  base_protocol_version_id: string
  base_protocol_version: string
  title: string
  rationale: string
  proposed_changes: string
  state: ProtocolImprovementState
  generated_by: "human" | "aira_assisted"
  generation_id?: string | null
  generation_model?: string | null
  generation_snapshot?: AiraProtocolImprovementGeneration | null
  generation_receipt_digest?: string | null
  revision: number
  created_by_user_id: string
  reviewed_by_user_id?: string | null
  reviewed_at?: string | null
  applied_protocol_version_id?: string | null
  applied_protocol_version?: string | null
  applied_by_user_id?: string | null
  applied_at?: string | null
  created_at: string
  updated_at: string
  protocol?: {
    id: string
    uid: string
    name: string
    base_protocol_version: string
  } | null
  evidence: Array<{
    evidence_id: string
    source_snapshot: Record<string, unknown>
  }>
}

export interface ResearchAssetBundle {
  data_assets: DataAsset[]
  evidence: ResearchEvidence[]
  claims: ResearchClaim[]
  knowledge_items: ResearchKnowledgeItem[]
  protocol_improvements: ProtocolImprovementProposal[]
}

export interface DataAssetDraft {
  task_id: string
  name: string
  description: string
  kind: DataAssetKind
  external_uri: string
  media_type: string
  checksum: string
  data_schema: Record<string, unknown>
  metadata: Record<string, unknown>
  source: Record<string, unknown>
  change_summary: string
}

export interface EvidenceDraft {
  task_id: string
  run_id?: string
  action_id?: string
  kind: EvidenceKind
  artifact_type: EvidenceArtifactType
  artifact_id: string
  artifact_version: string
  summary: string
}

export interface ClaimDraft {
  task_id: string
  statement: string
  confidence?: number
  uncertainty: string
  evidence: Array<{
    evidence_id: string
    relation: ClaimEvidenceRelation
    rationale: string
  }>
  aira_generation?: AiraClaimGeneration
  aira_receipt?: string
}

export interface AiraClaimGeneration {
  id: string
  model: string
  generated_at: string
  context_digest: string
  instruction: string
  source_snapshot: Record<string, unknown>
  output: {
    statement: string
    confidence?: number | null
    uncertainty: string
    evidence: Array<{
      evidence_id: string
      relation: ClaimEvidenceRelation
      rationale: string
    }>
  }
}

export interface AiraClaimDraftRequest {
  task_id: string
  evidence_ids: string[]
  instruction: string
}

export interface KnowledgeSuggestionDraft {
  task_id: string
  title: string
  body: string
  kind: ResearchKnowledgeKind
  tags: string[]
  evidence_ids: string[]
}

export interface ProtocolImprovementDraft {
  task_id: string
  protocol_id: string
  title: string
  rationale: string
  proposed_changes: string
  evidence_ids: string[]
  aira_generation?: AiraProtocolImprovementGeneration
  aira_receipt?: string
}

export interface AiraProtocolImprovementGeneration {
  id: string
  model: string
  generated_at: string
  context_digest: string
  instruction: string
  source_snapshot: Record<string, unknown>
  output: {
    title: string
    rationale: string
    proposed_changes: string
  }
}

export interface AiraProtocolImprovementDraftRequest {
  task_id: string
  protocol_id: string
  evidence_ids: string[]
  instruction: string
}

export interface AssetPreview<T> {
  preview_digest: string
  command: T
  destination: { task_id: string, task_title: string, project_id?: string, project_name?: string }
  effect: string | Record<string, unknown>
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (data === null)
    throw new Error("Research asset service returned no data")
  return data
}

export function fetchResearchAssets(taskId: string) {
  return getData<ResearchAssetBundle>({
    url: `/research-assets/tasks/${taskId}`,
    metadata: { showError: false },
  })
}

export function previewDataAsset(payload: DataAssetDraft) {
  return getData<AssetPreview<DataAssetDraft>>({
    url: "/research-assets/data-assets/preview",
    method: "POST",
    data: payload,
  })
}

export function createDataAsset(payload: DataAssetDraft & { preview_digest: string }) {
  return getData<DataAsset>({
    url: "/research-assets/data-assets",
    method: "POST",
    data: payload,
  })
}

export function updateDataAssetStatus(asset: DataAsset, status: "draft" | "ready" | "archived") {
  return getData<DataAsset>({
    url: `/research-assets/data-assets/${asset.id}/status`,
    method: "PATCH",
    data: { expected_status: asset.status, status },
  })
}

export function previewEvidence(payload: EvidenceDraft) {
  return getData<AssetPreview<EvidenceDraft>>({
    url: "/research-assets/evidence/preview",
    method: "POST",
    data: payload,
  })
}

export function createEvidence(payload: EvidenceDraft & { preview_digest: string }) {
  return getData<ResearchEvidence>({
    url: "/research-assets/evidence",
    method: "POST",
    data: payload,
  })
}

export function reviewEvidence(evidence: ResearchEvidence, qualityState: "validated" | "rejected") {
  return getData<ResearchEvidence>({
    url: `/research-assets/evidence/${evidence.id}/review`,
    method: "POST",
    data: {
      expected_quality_state: evidence.quality_state,
      quality_state: qualityState,
      validation_report: { reviewed_in: "research_task_workbench" },
    },
  })
}

export function previewClaim(payload: ClaimDraft) {
  return getData<AssetPreview<ClaimDraft>>({
    url: "/research-assets/claims/preview",
    method: "POST",
    data: payload,
  })
}

export function draftClaimWithAira(payload: AiraClaimDraftRequest) {
  return getData<ClaimDraft>({
    url: "/research-assets/claims/aira-draft",
    method: "POST",
    data: payload,
  })
}

export function createClaim(payload: ClaimDraft & { preview_digest: string }) {
  return getData<ResearchClaim>({
    url: "/research-assets/claims",
    method: "POST",
    data: payload,
  })
}

export function reviewClaim(claim: ResearchClaim, state: "reviewed" | "rejected") {
  return getData<ResearchClaim>({
    url: `/research-assets/claims/${claim.id}/review`,
    method: "POST",
    data: {
      expected_revision: claim.revision,
      expected_state: claim.state,
      state,
    },
  })
}

export function previewKnowledgeSuggestion(payload: KnowledgeSuggestionDraft) {
  return getData<AssetPreview<KnowledgeSuggestionDraft>>({
    url: "/research-assets/knowledge-suggestions/preview",
    method: "POST",
    data: payload,
  })
}

export function createKnowledgeSuggestion(payload: KnowledgeSuggestionDraft & { preview_digest: string }) {
  return getData<ResearchKnowledgeItem>({
    url: "/research-assets/knowledge-suggestions",
    method: "POST",
    data: payload,
  })
}

export function previewProtocolImprovement(payload: ProtocolImprovementDraft) {
  return getData<AssetPreview<ProtocolImprovementDraft>>({
    url: "/research-assets/protocol-improvements/preview",
    method: "POST",
    data: payload,
  })
}

export function draftProtocolImprovementWithAira(payload: AiraProtocolImprovementDraftRequest) {
  return getData<ProtocolImprovementDraft>({
    url: "/research-assets/protocol-improvements/aira-draft",
    method: "POST",
    data: payload,
  })
}

export function createProtocolImprovement(payload: ProtocolImprovementDraft & { preview_digest: string }) {
  return getData<ProtocolImprovementProposal>({
    url: "/research-assets/protocol-improvements",
    method: "POST",
    data: payload,
  })
}

export function fetchProtocolImprovement(proposalId: string) {
  return getData<ProtocolImprovementProposal>({
    url: `/research-assets/protocol-improvements/${proposalId}`,
    metadata: { showError: false },
  })
}

export function reviewProtocolImprovement(
  proposal: ProtocolImprovementProposal,
  state: "reviewed" | "rejected",
) {
  return getData<ProtocolImprovementProposal>({
    url: `/research-assets/protocol-improvements/${proposal.id}/review`,
    method: "POST",
    data: {
      expected_revision: proposal.revision,
      expected_state: proposal.state,
      state,
    },
  })
}

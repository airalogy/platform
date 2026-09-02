import { request } from "../request"
import { fetchBlobContent } from "./common"

export type OwnerScope = "personal" | "lab" | "project"
export type KnowledgeVisibility = "private" | "lab" | "project" | "restricted"
export type KnowledgeKind = "reference" | "note" | "method" | "decision" | "finding"
export type KnowledgeState = "suggested" | "draft" | "reviewed" | "superseded" | "archived"
export type PaperImportSource = "doi" | "url" | "bibtex" | "ris" | "manual"

export interface KnowledgeScope {
  scope_type: OwnerScope
  lab_id?: string
  project_id?: string
  visibility: KnowledgeVisibility
}

export interface Paper {
  id: string
  doi?: string | null
  title: string
  abstract: string
  publication_year?: number | null
  first_author: string
  authors: string[]
  venue: string
  identifiers: Record<string, string>
  candidate_fingerprint: string
  metadata_source: string
  created_at: string
  updated_at: string
}

export interface ResearchFileSummary {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  relationship_type: string
}

export interface PaperLibraryEntry {
  id: string
  scope_type: OwnerScope
  owner_user_id?: string | null
  lab_id?: string | null
  project_id?: string | null
  visibility: KnowledgeVisibility
  tags: string[]
  notes: string
  source_type: string
  source_url?: string | null
  source_metadata?: Record<string, unknown>
  paper: Paper
  files?: ResearchFileSummary[]
  project_ids?: string[]
  collection_ids?: string[]
  created_at: string
  updated_at?: string
}

export interface PaperImportCandidate {
  id: string
  title: string
  publication_year?: number | null
  first_author: string
  doi?: string | null
}

export interface PaperImportPreview {
  id: string
  status: string
  expires_at: string
  preview_digest: string
  paper: Omit<Paper, "id" | "created_at" | "updated_at">
  duplicate: {
    kind: "none" | "exact_doi" | "candidate_conflict"
    candidate_ids: string[]
    candidates: PaperImportCandidate[]
  }
  impact: {
    destination: {
      scope_type: OwnerScope
      owner_user_id?: string | null
      lab_id?: string | null
      project_id?: string | null
    }
    visibility: KnowledgeVisibility
    file_id?: string | null
    requires_explicit_duplicate_decision: boolean
  }
}

export interface KnowledgeItem {
  id: string
  scope_type: OwnerScope
  owner_user_id?: string | null
  lab_id?: string | null
  project_id?: string | null
  visibility: KnowledgeVisibility
  kind: KnowledgeKind
  state: KnowledgeState
  title: string
  body: string
  tags: string[]
  revision: number
  derived_from_id?: string | null
  generated_by: "human" | "aira"
  created_by_user_id: string
  reviewed_by_user_id?: string | null
  reviewed_at?: string | null
  paper_library_entry_ids: string[]
  research_file_ids: string[]
  evidence_sources: Array<{
    knowledge_revision: number
    evidence_id: string
    source_snapshot: {
      kind: string
      artifact_type: string
      artifact_id: string
      artifact_version: string
      summary: string
      quality_state: string
      validation_report: Record<string, unknown>
    }
  }>
  created_at: string
  updated_at: string
}

export interface KnowledgePublishPreview {
  preview_digest: string
  impact: {
    source_item_id: string
    source_revision: number
    target: Record<string, string | null>
    paper_metadata_entries_to_publish: string[]
    private_files_omitted: string[]
    new_state: "draft"
  }
}

export interface PaperCollection {
  id: string
  name: string
  description: string
  scope_type: OwnerScope
  lab_id?: string | null
  project_id?: string | null
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (data === null)
    throw new Error("Knowledge service returned no data")
  return data
}

export function fetchPapers(params: Omit<KnowledgeScope, "visibility"> & {
  q?: string
  tag?: string
  page?: number
  pageSize?: number
}) {
  return getData<{ items: PaperLibraryEntry[], page: number, page_size: number }>({
    url: "/knowledge/papers",
    params: {
      scope_type: params.scope_type,
      lab_id: params.lab_id,
      project_id: params.project_id,
      q: params.q || undefined,
      tag: params.tag || undefined,
      page: params.page || 1,
      page_size: params.pageSize || 20,
    },
    metadata: { showError: false },
  })
}

export function fetchPaper(entryId: string) {
  return getData<PaperLibraryEntry>({
    url: `/knowledge/papers/${entryId}`,
    metadata: { showError: false },
  })
}

export function updatePaperEntry(entryId: string, payload: { tags?: string[], notes?: string }) {
  return getData<PaperLibraryEntry>({
    url: `/knowledge/papers/${entryId}`,
    method: "PATCH",
    data: payload,
  })
}

export function previewPaperImport(payload: KnowledgeScope & {
  source_type: PaperImportSource
  source: string
  metadata: Record<string, unknown>
}) {
  return getData<PaperImportPreview>({
    url: "/knowledge/papers/import/preview",
    method: "POST",
    data: payload,
  })
}

export function previewPdfImport(payload: KnowledgeScope & {
  file: File
  title: string
  doi?: string
  authors: string[]
  publication_year?: number | null
  abstract?: string
  venue?: string
}) {
  const data = new FormData()
  data.append("file", payload.file)
  data.append("scope_type", payload.scope_type)
  data.append("visibility", payload.visibility)
  data.append("title", payload.title)
  data.append("authors_json", JSON.stringify(payload.authors))
  if (payload.lab_id)
    data.append("lab_id", payload.lab_id)
  if (payload.project_id)
    data.append("project_id", payload.project_id)
  if (payload.doi)
    data.append("doi", payload.doi)
  if (payload.publication_year)
    data.append("publication_year", String(payload.publication_year))
  if (payload.abstract)
    data.append("abstract", payload.abstract)
  if (payload.venue)
    data.append("venue", payload.venue)
  return getData<PaperImportPreview>({
    url: "/knowledge/papers/import/pdf/preview",
    method: "POST",
    data,
  })
}

export function confirmPaperImport(draftId: string, payload: {
  preview_digest: string
  duplicate_resolution: "create_new" | "use_existing"
  existing_paper_id?: string
  confirm_distinct?: boolean
}) {
  return getData<PaperLibraryEntry>({
    url: `/knowledge/papers/import/${draftId}/confirm`,
    method: "POST",
    data: payload,
  })
}

export function exportPaper(entryId: string, format: "bibtex" | "ris") {
  return fetchBlobContent(`/knowledge/papers/${entryId}/export?format=${format}`)
}

export function fetchCollections(scope: Omit<KnowledgeScope, "visibility">) {
  return getData<{ items: PaperCollection[] }>({
    url: "/knowledge/collections",
    params: scope,
    metadata: { showError: false },
  })
}

export function createCollection(payload: Omit<KnowledgeScope, "visibility"> & {
  name: string
  description?: string
}) {
  return getData<PaperCollection>({ url: "/knowledge/collections", method: "POST", data: payload })
}

export function assignCollectionEntries(collectionId: string, libraryEntryIds: string[]) {
  return getData<{ collection_id: string, library_entry_ids: string[] }>({
    url: `/knowledge/collections/${collectionId}/entries`,
    method: "PUT",
    data: { library_entry_ids: libraryEntryIds },
  })
}

export function addPaperToCollection(collectionId: string, entryId: string) {
  return getData<{ collection_id: string, library_entry_id: string }>({
    url: `/knowledge/collections/${collectionId}/entries/${entryId}`,
    method: "POST",
  })
}

export function removePaperFromCollection(collectionId: string, entryId: string) {
  return getData<{ collection_id: string, library_entry_id: string }>({
    url: `/knowledge/collections/${collectionId}/entries/${entryId}`,
    method: "DELETE",
  })
}

export function fetchKnowledgeItems(params: Omit<KnowledgeScope, "visibility"> & {
  q?: string
  kind?: KnowledgeKind
  state?: KnowledgeState
  page?: number
  pageSize?: number
}) {
  return getData<{ items: KnowledgeItem[], page: number, page_size: number }>({
    url: "/knowledge/items",
    params: {
      scope_type: params.scope_type,
      lab_id: params.lab_id,
      project_id: params.project_id,
      q: params.q || undefined,
      kind: params.kind || undefined,
      state: params.state || undefined,
      page: params.page || 1,
      page_size: params.pageSize || 20,
    },
    metadata: { showError: false },
  })
}

export function fetchKnowledgeItem(itemId: string) {
  return getData<KnowledgeItem>({
    url: `/knowledge/items/${itemId}`,
    metadata: { showError: false },
  })
}

export function createKnowledgeItem(payload: KnowledgeScope & {
  kind: KnowledgeKind
  title: string
  body: string
  tags: string[]
  paper_library_entry_ids?: string[]
  research_file_ids?: string[]
}) {
  return getData<KnowledgeItem>({ url: "/knowledge/items", method: "POST", data: payload })
}

export function updateKnowledgeItem(itemId: string, payload: {
  expected_revision: number
  title?: string
  body?: string
  kind?: KnowledgeKind
  tags?: string[]
  change_summary?: string
}) {
  return getData<KnowledgeItem>({
    url: `/knowledge/items/${itemId}`,
    method: "PATCH",
    data: payload,
  })
}

export function reviewKnowledgeItem(itemId: string, revision: number, note = "") {
  return getData<KnowledgeItem>({
    url: `/knowledge/items/${itemId}/review`,
    method: "POST",
    data: { expected_revision: revision, note },
  })
}

export function previewKnowledgePublish(itemId: string, payload: {
  target_scope_type: "project" | "lab"
  target_lab_id?: string
  target_project_id?: string
}) {
  return getData<KnowledgePublishPreview>({
    url: `/knowledge/items/${itemId}/publish/preview`,
    method: "POST",
    data: payload,
  })
}

export function confirmKnowledgePublish(itemId: string, payload: {
  target_scope_type: "project" | "lab"
  target_lab_id?: string
  target_project_id?: string
  expected_revision: number
  preview_digest: string
}) {
  return getData<KnowledgeItem>({
    url: `/knowledge/items/${itemId}/publish/confirm`,
    method: "POST",
    data: payload,
  })
}

export async function fetchResearchFile(fileId: string, mode: "preview" | "download") {
  const token = await getData<{ url: string, mode: string, expires_at: string }>({
    url: `/knowledge/files/${fileId}/token`,
    method: "POST",
    data: { mode },
  })
  const blob = await fetchBlobContent(token.url)
  if (!blob)
    throw new Error("Research file returned no content")
  return blob
}

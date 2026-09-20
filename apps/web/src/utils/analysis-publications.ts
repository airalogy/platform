import type { AnalysisPublicationDraft } from "@/service/api/analysis-publications"

/** One frozen command is used for both preview and confirmation. */
export function analysisPublicationCommand(draft: AnalysisPublicationDraft): AnalysisPublicationDraft {
  return {
    task_id: draft.task_id,
    title: draft.title.trim(),
    summary: draft.summary.trim(),
    sections: draft.sections.filter(section => section.fields.length).map(section => ({ section_id: section.section_id, fields: [...section.fields] })),
    interpretation_revision_id: draft.interpretation_revision_id,
  }
}

/** getRandomValues also works on private HTTP deployments without randomUUID. */
export function publicationConfirmationKey(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0F) | 0x40
  bytes[8] = (bytes[8] & 0x3F) | 0x80
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("")
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

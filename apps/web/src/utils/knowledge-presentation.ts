const artifactTypeKeys = {
  record: "page.research.artifactType.record",
  data_asset: "page.research.artifactType.data_asset",
  knowledge: "page.research.artifactType.knowledge",
  paper_library_entry: "page.research.artifactType.paper_library_entry",
  action_output: "page.research.artifactType.action_output",
  analysis_publication: "page.research.artifactType.analysis_publication",
  external: "page.research.artifactType.external",
} as const

/** Unknown historical source types must not be mislabeled as DataAssets. */
export function researchArtifactTypeKey(value: string) {
  return Object.prototype.hasOwnProperty.call(artifactTypeKeys, value)
    ? artifactTypeKeys[value as keyof typeof artifactTypeKeys]
    : artifactTypeKeys.external
}

/** Content digests identify snapshots; they are not sequential revisions. */
export function researchArtifactVersionLabel(type: string, version: string | null | undefined, compact = false): string {
  if (!version)
    return ""
  if (type === "action_output" || type === "analysis_publication")
    return `SHA-256 ${compact && version.length > 12 ? `${version.slice(0, 12)}…` : version}`
  return `v${version}`
}

/** A view hint never selects a Knowledge identity or changes its authorization. */
export function knowledgeViewFromQuery(value: unknown): "papers" | "items" {
  return value === "items" ? "items" : "papers"
}

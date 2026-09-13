interface EnvironmentPin {
  source_id: string
  source_revision_id: string
  available: boolean
}

/** Convert suggested current environment IDs into explicitly displayed, fixed revisions. */
export function resolveResearchComputeSelection(legacyIds: string[], exactIds: string[], latest: EnvironmentPin[], revisions: EnvironmentPin[]): string[] {
  if (legacyIds.length && exactIds.length)
    throw new Error("conflictingComputeSelection")
  const ids = exactIds.length
    ? [...exactIds]
    : legacyIds.map((id) => {
      const environment = latest.find(item => item.source_id === id && item.available)
      if (!environment)
        throw new Error("unknownComputeEnvironment")
      return environment.source_revision_id
    })
  const environments = new Set<string>()
  for (const id of ids) {
    const environment = revisions.find(item => item.source_revision_id === id && item.available)
    if (!environment || environments.has(environment.source_id))
      throw new Error("conflictingComputeRevision")
    environments.add(environment.source_id)
  }
  return ids
}

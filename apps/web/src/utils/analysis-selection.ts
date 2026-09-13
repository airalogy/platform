export interface AnalysisRecordReference {
  id: string
  version: number
}

export interface AnalysisRecordFilters {
  user_id?: string
  protocol_version?: string
  number?: number
  version?: number
  q?: string
}

export type AnalysisSelection = {
  mode: "latest"
  filters: AnalysisRecordFilters
  records?: never
} | {
  mode: "selected"
  filters: AnalysisRecordFilters
  records: AnalysisRecordReference[]
}

export interface AnalysisSelectionTransfer {
  userId: string
  projectId: string
  protocolId: string
  selection: AnalysisSelection
}

const TRANSFER_PREFIX = "airalogy.analysis-selection."
const TRANSFER_TTL_MS = 10 * 60 * 1000
const MAX_TRANSFER_RECORDS = 5000
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function cleanSelection(selection: AnalysisSelection): AnalysisSelection {
  if (!selection || !["latest", "selected"].includes(selection.mode))
    throw new Error("Invalid analysis selection")

  const filters: AnalysisRecordFilters = {}
  for (const key of ["user_id", "protocol_version", "q"] as const) {
    const value = selection.filters?.[key]
    if (value !== undefined) {
      if (typeof value !== "string")
        throw new Error("Invalid analysis filter")
      if (value.trim())
        filters[key] = value.trim()
    }
  }
  for (const key of ["number", "version"] as const) {
    const value = selection.filters?.[key]
    if (value !== undefined) {
      if (!Number.isSafeInteger(value) || value < 1)
        throw new Error("Invalid analysis filter")
      filters[key] = value
    }
  }
  if (selection.mode === "latest")
    return { mode: "latest", filters }

  if (!Array.isArray(selection.records) || !selection.records.length || selection.records.length > MAX_TRANSFER_RECORDS)
    throw new Error("Invalid selected Record count")
  const seen = new Set<string>()
  const records = selection.records.map((record) => {
    if (!record || !UUID_PATTERN.test(record.id) || !Number.isSafeInteger(record.version) || record.version < 1 || seen.has(record.id))
      throw new Error("Invalid selected Record reference")
    seen.add(record.id)
    return { id: record.id, version: record.version }
  })
  // Explicit selection takes precedence over filter criteria; selections may
  // intentionally span multiple pages and previously applied filters.
  return { mode: "selected", filters: {}, records }
}

/** Short-lived navigation hint only: never a permission grant or a Record cache. */
export function createAnalysisSelectionTransfer(
  input: AnalysisSelectionTransfer,
  storage: Storage = window.sessionStorage,
  now = Date.now(),
): string {
  if (![input.userId, input.projectId, input.protocolId].every(id => UUID_PATTERN.test(id)))
    throw new Error("Invalid analysis scope")
  const selection = cleanSelection(input.selection)
  for (let index = storage.length - 1; index >= 0; index -= 1) {
    const key = storage.key(index)
    if (!key?.startsWith(TRANSFER_PREFIX))
      continue
    try {
      const previous = JSON.parse(storage.getItem(key) || "null")
      if (!previous || typeof previous.expiresAt !== "number" || previous.expiresAt <= now)
        storage.removeItem(key)
    }
    catch {
      storage.removeItem(key)
    }
  }
  // getRandomValues also works on HTTP intranet installations where randomUUID
  // may be unavailable because the browser does not consider them secure contexts.
  const token = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join("")
  storage.setItem(`${TRANSFER_PREFIX}${token}`, JSON.stringify({
    userId: input.userId,
    projectId: input.projectId,
    protocolId: input.protocolId,
    selection,
    expiresAt: now + TRANSFER_TTL_MS,
  }))
  return token
}

/** Consume once and validate the signed-in identity and destination scope. */
export function consumeAnalysisSelectionTransfer(
  token: string,
  scope: Omit<AnalysisSelectionTransfer, "selection">,
  storage: Storage = window.sessionStorage,
  now = Date.now(),
): AnalysisSelection | null {
  if (!/^[0-9a-f]{32}$/.test(token))
    return null
  const key = `${TRANSFER_PREFIX}${token}`
  try {
    const raw = storage.getItem(key)
    storage.removeItem(key)
    if (!raw)
      return null
    const saved = JSON.parse(raw)
    if (saved.userId !== scope.userId || saved.projectId !== scope.projectId || saved.protocolId !== scope.protocolId)
      return null
    if (typeof saved.expiresAt !== "number" || saved.expiresAt <= now || saved.expiresAt > now + TRANSFER_TTL_MS)
      return null
    return cleanSelection(saved.selection)
  }
  catch {
    return null
  }
}

export function discardAnalysisSelectionTransfer(token: string, storage: Storage = window.sessionStorage) {
  if (/^[0-9a-f]{32}$/.test(token))
    storage.removeItem(`${TRANSFER_PREFIX}${token}`)
}

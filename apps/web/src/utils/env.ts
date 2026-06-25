const warnedKeys = new Set<string>()

function warnOnce(key: string, message: string) {
  if (!import.meta.env.DEV) {
    return
  }
  if (warnedKeys.has(key)) {
    return
  }
  warnedKeys.add(key)
  console.warn(message)
}

function parseNumberEnv(key: keyof Env.ImportMeta, fallback: number, options?: { min?: number, max?: number }) {
  const rawValue = import.meta.env[key]
  if (rawValue == null || rawValue === "") {
    warnOnce(String(key), `[env] ${String(key)} is not set. Using default: ${fallback}`)
    return fallback
  }

  const parsed = Number(rawValue)
  if (!Number.isFinite(parsed)) {
    warnOnce(String(key), `[env] ${String(key)} is not a valid number ("${rawValue}"). Using default: ${fallback}`)
    return fallback
  }

  if (options?.min != null && parsed < options.min) {
    warnOnce(String(key), `[env] ${String(key)} is below minimum (${options.min}). Using default: ${fallback}`)
    return fallback
  }

  if (options?.max != null && parsed > options.max) {
    warnOnce(String(key), `[env] ${String(key)} is above maximum (${options.max}). Using default: ${fallback}`)
    return fallback
  }

  return parsed
}

function parseYesNoEnv(key: keyof Env.ImportMeta, fallback = false) {
  const rawValue = import.meta.env[key]
  if (rawValue == null || rawValue === "") {
    return fallback
  }

  if (rawValue === "Y") {
    return true
  }

  if (rawValue === "N") {
    return false
  }

  warnOnce(String(key), `[env] ${String(key)} must be "Y" or "N" ("${rawValue}"). Using default: ${fallback ? "Y" : "N"}`)
  return fallback
}

function parseStringEnv(key: keyof Env.ImportMeta) {
  return import.meta.env[key]?.trim() || undefined
}

export function getRecordDeleteGraceDays() {
  return parseNumberEnv("VITE_RECORD_DELETE_GRACE_DAYS", 7, { min: 1 })
}

export function getChinaComplianceFooterConfig() {
  const icpRecordNumber = parseStringEnv("VITE_ICP_RECORD_NUMBER")
  const policeRecordNumber = parseStringEnv("VITE_POLICE_RECORD_NUMBER")
  const policeRecordCode = parseStringEnv("VITE_POLICE_RECORD_CODE")
  const policeRecordUrl = parseStringEnv("VITE_POLICE_RECORD_URL")
    || (policeRecordCode ? `https://beian.mps.gov.cn/#/query/webSearch?code=${encodeURIComponent(policeRecordCode)}` : undefined)

  return {
    visible: parseYesNoEnv("VITE_CHINA_COMPLIANCE_FOOTER") && Boolean(icpRecordNumber || policeRecordNumber),
    icpRecordNumber,
    icpRecordUrl: parseStringEnv("VITE_ICP_RECORD_URL") || "https://beian.miit.gov.cn/",
    policeRecordNumber,
    policeRecordUrl,
    policeRecordIconUrl: parseStringEnv("VITE_POLICE_RECORD_ICON_URL"),
  }
}

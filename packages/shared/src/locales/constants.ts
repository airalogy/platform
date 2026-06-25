export const DEFAULT_LOCALE: I18n.LangType = "en-US"

// Extend this list when adding new languages.
export const LOCALE_OPTIONS: I18n.LangOption[] = [
  { key: "en-US", label: "English" },
  { key: "zh-CN", label: "中文" },
]

export const SUPPORTED_LOCALES: I18n.LangType[] = LOCALE_OPTIONS.map(({ key }) => key)

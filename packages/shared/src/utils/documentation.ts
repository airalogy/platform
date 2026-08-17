export type DocumentationSection = "user-guide" | "lab-admin" | "self-hosting" | "developer"

const DEFAULT_DOCUMENTATION_URL = "/docs/"

function withTrailingSlash(value: string) {
  return value.endsWith("/") ? value : `${value}/`
}

function documentationBaseUrl(documentationUrl: string | undefined) {
  const configuredBase = documentationUrl?.trim() || DEFAULT_DOCUMENTATION_URL
  return new URL(withTrailingSlash(configuredBase), window.location.origin)
}

export function documentationLocale(locale: string): "en" | "zh" {
  return locale.toLowerCase() === "zh-cn" ? "zh" : "en"
}

export function documentationPageUrl(
  documentationUrl: string | undefined,
  locale: string,
  page: string,
) {
  const normalizedPage = page.replace(/^\/+/, "")
  return new URL(
    `${documentationLocale(locale)}/${normalizedPage}`,
    documentationBaseUrl(documentationUrl),
  ).toString()
}

export function documentationSectionUrl(
  documentationUrl: string | undefined,
  locale: string,
  section: DocumentationSection,
) {
  return documentationPageUrl(documentationUrl, locale, `${section}/`)
}

export function configuredLinkUrl(value: string) {
  return new URL(value, window.location.origin).toString()
}

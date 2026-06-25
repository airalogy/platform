import type { RouteLocationNormalized } from "vue-router"

export interface SeoMetaInput {
  title?: string | null
  description?: string | null
  canonical?: string | null
  robots?: string | null
  ogType?: "website" | "article"
  image?: string | null
  keywords?: string[] | null
  publishedTime?: string | null
  modifiedTime?: string | null
  jsonLd?: Record<string, unknown> | Array<Record<string, unknown>> | null
}

const SITE_NAME = "Airalogy"
const DEFAULT_DESCRIPTION = "Discover public research protocols, collaborative projects, and reproducible workflows on Airalogy."
const DEFAULT_IMAGE_PATH = "/images/hero_placeholder.png"
const MANAGED_ATTR = "data-airalogy-seo"
const NOINDEX_ROUTE_NAMES = new Set([
  "403",
  "404",
  "500",
  "add-protocol-record",
  "forget-password",
  "hub-detail-discussion",
  "hub-detail-protocol",
  "hub-detail-record",
  "hub-search",
  "login",
  "not-found",
  "protocol-discussion-detail",
  "protocol-discussions",
  "protocol-info-apply-protocol",
  "protocol-record-report",
  "protocol-records",
  "protocol-settings",
  "project-members",
  "project-settings",
  "sign-up",
])

function normalizeText(text: string | null | undefined, maxLength: number) {
  if (!text) {
    return ""
  }

  const normalized = text.replace(/\s+/g, " ").trim()
  if (!normalized) {
    return ""
  }

  if (normalized.length <= maxLength) {
    return normalized
  }

  return `${normalized.slice(0, maxLength - 1).trimEnd()}...`
}

function getManagedSelector(selector: string) {
  return `${selector}[${MANAGED_ATTR}="true"]`
}

function upsertMetaTag(identifier: { name?: string, property?: string }, content?: string | null) {
  const attrName = identifier.name ? "name" : "property"
  const attrValue = identifier.name || identifier.property
  if (!attrValue) {
    return
  }

  const selector = identifier.name
    ? `meta[name="${identifier.name}"]`
    : `meta[property="${identifier.property}"]`
  const existing = document.head.querySelector<HTMLMetaElement>(selector)

  if (!content) {
    existing?.remove()
    return
  }

  const element = existing || document.createElement("meta")
  element.setAttribute(attrName, attrValue)
  element.setAttribute("content", content)
  element.setAttribute(MANAGED_ATTR, "true")
  if (!existing) {
    document.head.appendChild(element)
  }
}

function upsertLinkTag(rel: string, href?: string | null) {
  const selector = `link[rel="${rel}"]`
  const existing = document.head.querySelector<HTMLLinkElement>(selector)

  if (!href) {
    existing?.remove()
    return
  }

  const element = existing || document.createElement("link")
  element.setAttribute("rel", rel)
  element.setAttribute("href", href)
  element.setAttribute(MANAGED_ATTR, "true")
  if (!existing) {
    document.head.appendChild(element)
  }
}

function upsertJsonLdScript(jsonLd?: SeoMetaInput["jsonLd"]) {
  const selector = getManagedSelector("script[type=\"application/ld+json\"]")
  const existing = document.head.querySelector<HTMLScriptElement>(selector)

  if (!jsonLd) {
    existing?.remove()
    return
  }

  const element = existing || document.createElement("script")
  element.setAttribute("type", "application/ld+json")
  element.setAttribute(MANAGED_ATTR, "true")
  element.textContent = JSON.stringify(jsonLd)
  if (!existing) {
    document.head.appendChild(element)
  }
}

function resolveCurrentUrl() {
  if (typeof window === "undefined") {
    return null
  }

  return `${window.location.origin}${window.location.pathname}`
}

export function buildSeoUrl(path?: string | null) {
  if (!path) {
    return resolveCurrentUrl()
  }

  if (/^https?:\/\//.test(path)) {
    return path
  }

  if (typeof window === "undefined") {
    return path
  }

  return new URL(path, `${window.location.origin}/`).toString()
}

export function buildPublicProjectPath(payload: {
  labUid?: string | null
  projectUid?: string | null
}) {
  const { labUid, projectUid } = payload
  if (!labUid || !projectUid) {
    return null
  }

  return `/labs/${encodeURIComponent(labUid)}/projects/${encodeURIComponent(projectUid)}/protocols`
}

export function buildPublicProtocolPath(payload: {
  labUid?: string | null
  projectUid?: string | null
  protocolUid?: string | null
}) {
  const { labUid, projectUid, protocolUid } = payload
  if (!labUid || !projectUid || !protocolUid) {
    return null
  }

  return `/labs/${encodeURIComponent(labUid)}/projects/${encodeURIComponent(projectUid)}/protocols/${encodeURIComponent(protocolUid)}/protocol`
}

function getRouteCanonicalPath(route: RouteLocationNormalized) {
  const { labUid, projectUid, protocolUid } = route.params as Record<string, string | undefined>
  const routeName = String(route.name || "")

  if (routeName.startsWith("hub-detail-")) {
    return buildPublicProtocolPath({ labUid, projectUid, protocolUid })
  }

  return route.path
}

function getRouteRobots(route: RouteLocationNormalized) {
  const routeName = String(route.name || "")

  if (NOINDEX_ROUTE_NAMES.has(routeName)) {
    return "noindex,follow"
  }

  if (!route.meta.constant && !route.meta.allowGuest) {
    return "noindex,follow"
  }

  return "index,follow"
}

function getRouteDescription(route: RouteLocationNormalized) {
  const routeName = String(route.name || "")

  switch (routeName) {
    case "hub-list":
      return "Explore public protocols shared on Airalogy."
    case "project-protocols":
      return "Browse public protocols and shared research assets on Airalogy."
    case "protocol-detail":
      return "Read a public protocol on Airalogy."
    default:
      return DEFAULT_DESCRIPTION
  }
}

export function applySeoMeta(input: SeoMetaInput) {
  if (typeof document === "undefined") {
    return
  }

  const title = normalizeText(input.title || SITE_NAME, 120) || SITE_NAME
  const description = normalizeText(input.description || DEFAULT_DESCRIPTION, 180) || DEFAULT_DESCRIPTION
  const canonical = buildSeoUrl(input.canonical)
  const image = buildSeoUrl(input.image || DEFAULT_IMAGE_PATH)
  const robots = input.robots || "index,follow"
  const keywords = input.keywords?.filter(Boolean).join(", ") || null
  const ogType = input.ogType || "website"

  document.title = title

  upsertMetaTag({ name: "description" }, description)
  upsertMetaTag({ name: "robots" }, robots)
  upsertMetaTag({ name: "keywords" }, keywords)

  upsertMetaTag({ property: "og:site_name" }, SITE_NAME)
  upsertMetaTag({ property: "og:type" }, ogType)
  upsertMetaTag({ property: "og:title" }, title)
  upsertMetaTag({ property: "og:description" }, description)
  upsertMetaTag({ property: "og:url" }, canonical)
  upsertMetaTag({ property: "og:image" }, image)
  upsertMetaTag({ property: "article:published_time" }, input.publishedTime)
  upsertMetaTag({ property: "article:modified_time" }, input.modifiedTime)

  upsertMetaTag({ name: "twitter:card" }, image ? "summary_large_image" : "summary")
  upsertMetaTag({ name: "twitter:title" }, title)
  upsertMetaTag({ name: "twitter:description" }, description)
  upsertMetaTag({ name: "twitter:url" }, canonical)
  upsertMetaTag({ name: "twitter:image" }, image)

  upsertLinkTag("canonical", canonical)
  upsertJsonLdScript(input.jsonLd)
}

export function applyRouteSeo(route: RouteLocationNormalized, title: string) {
  applySeoMeta({
    title,
    description: getRouteDescription(route),
    canonical: getRouteCanonicalPath(route),
    robots: getRouteRobots(route),
    ogType: "website",
    image: DEFAULT_IMAGE_PATH,
  })
}

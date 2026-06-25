import type { RouteLocationNormalized, Router } from "vue-router"
import { useRouteStore } from "@/store/modules/route"

/**
 * Configuration for route relevance checking
 */
const RELEVANCE_CONFIG = {
  // Minimum number of common path segments to consider routes relevant
  minCommonSegments: 2,
  // Routes with these prefixes are considered relevant to each other
  relevantPrefixes: ["lab", "project", "protocol", "hub", "admin"],
}

/**
 * Check if two routes are relevant to each other
 * Routes are considered relevant if they share context (same lab, project, etc.)
 *
 * @param from - Source route
 * @param to - Target route
 * @returns true if routes are relevant, false otherwise
 */
function areRoutesRelevant(from: RouteLocationNormalized, to: RouteLocationNormalized): boolean {
  // Handle initial navigation or missing route info
  if (!from.name || !to.name || from.name === to.name) {
    return true
  }

  // Check for common path segments
  const fromSegments = from.path.split("/").filter(Boolean)
  const toSegments = to.path.split("/").filter(Boolean)

  // Count common segments from the beginning
  let commonSegments = 0
  const maxLength = Math.min(fromSegments.length, toSegments.length)

  for (let i = 0; i < maxLength; i++) {
    if (fromSegments[i] === toSegments[i]) {
      commonSegments++
    }
    else {
      break
    }
  }

  // Routes are relevant if they have enough common path segments
  if (commonSegments >= RELEVANCE_CONFIG.minCommonSegments) {
    return true
  }

  // Check for relevant route name prefixes
  const fromPrefix = String(from.name).split("-")[0]
  const toPrefix = String(to.name).split("-")[0]

  if (fromPrefix === toPrefix && RELEVANCE_CONFIG.relevantPrefixes.includes(fromPrefix)) {
    return true
  }

  // Check for parent-child relationships through route parameters
  const fromParams = Object.keys(from.params)
  const toParams = Object.keys(to.params)

  // If routes share the same parameter keys, they might be related
  if (fromParams.length > 0 && toParams.length > 0) {
    const sharedParams = fromParams.filter(param =>
      toParams.includes(param) && from.params[param] === to.params[param],
    )

    // Routes are relevant if they share lab, project, or protocol parameters
    if (sharedParams.some(param => ["labUid", "projectUid", "protocolUid"].includes(param))) {
      return true
    }
  }

  return false
}

/**
 * Create clear breadcrumbs guard for router
 * Clears dynamic breadcrumbs only when navigating between unrelated routes
 *
 * @param router - Vue Router instance
 */
export function createClearBreadcrumbsGuard(router: Router) {
  router.beforeEach((to, from, next) => {
    const routeStore = useRouteStore()

    // Only clear breadcrumbs when routes are not relevant to each other
    if (!areRoutesRelevant(from, to)) {
      routeStore.clearDynamicBreadcrumbs()
    }

    next()
  })
}

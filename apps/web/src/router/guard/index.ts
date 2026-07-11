import type { Router } from "vue-router"
import { createAuthPingGuard } from "./authPing"
import { createCancelRequestGuard } from "./cancelRequest"
import { createClearBreadcrumbsGuard } from "./clearBreadcrumbs"
import { createInstanceGuard } from "./instance"
import { createPermissionGuard } from "./permission"
import { createSameRouteParamsGuard } from "./sameRouteParams"
import { createScrollToTopGuard } from "./scrollToTop"
import { createSpinWrapperGuard } from "./spinWrapper"
import { createDocumentTitleGuard } from "./title"
import { createUnsavedChangesGuard } from "./unsavedChanges"

/**
 * Router guard
 *
 * @param router - Router instance
 */
export function createRouterGuard(router: Router) {
  // The order is important here
  // We want to check for unsaved changes before other guards
  createUnsavedChangesGuard(router)
  // Clear breadcrumbs early before other guards potentially set new ones
  createClearBreadcrumbsGuard(router)
  createCancelRequestGuard(router)
  createInstanceGuard(router)
  createPermissionGuard(router)
  createAuthPingGuard(router)
  createSameRouteParamsGuard(router)
  createDocumentTitleGuard(router)
  createScrollToTopGuard(router)
  createSpinWrapperGuard(router)
}

import type { Router } from "vue-router"

/**
 * Create a guard for handling navigation to the same route with different params
 * This ensures component lifecycle hooks are properly triggered
 *
 * @param router - Router instance
 */
export function createSameRouteParamsGuard(router: Router) {
  router.beforeEach((to, from, next) => {
    if (to.name === from.name && to.path !== from.path) {
      // Force a component refresh when navigating to the same route but with different params
      to.meta.reload = true
      next()
    }
    else {
      next()
    }
  })
}

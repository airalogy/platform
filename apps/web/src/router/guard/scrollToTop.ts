import type { Router } from "vue-router"

/**
 * Create scroll to top guard for router
 * Automatically scrolls the page to top when navigating to a new route
 *
 * @param router - Vue Router instance
 */
export function createScrollToTopGuard(router: Router) {
  router.afterEach((to, from) => {
    // Only scroll to top if the route path has changed
    // This prevents unnecessary scrolling when only query params or hash changes
    if (to.path !== from.path) {
      // Use nextTick to ensure DOM has updated before scrolling
      window.scrollTo({
        top: 0,
        // behavior: "smooth", // Use smooth scrolling for better UX
      })
    }
  })
}

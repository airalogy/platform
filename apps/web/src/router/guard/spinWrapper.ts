import type { Router } from "vue-router"
import { useAppStore } from "@/store/modules/app"

/**
 * Create scroll to top guard for router
 * Automatically scrolls the page to top when navigating to a new route
 *
 * @param router - Vue Router instance
 */
export function createSpinWrapperGuard(router: Router) {
  const appStore = useAppStore()

  router.afterEach((to) => {
    appStore.setIsSpinWrapper(to.meta.useSpinWrapper || false)
  })
}

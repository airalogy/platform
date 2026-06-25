import type { Router } from "vue-router"
import { request } from "@/service/request"

export function createCancelRequestGuard(router: Router) {
  router.afterEach((to, from) => {
    // Don't cancel requests if navigating within the same route path
    if (to.path.startsWith(from.path) || from.path.startsWith(to.path)) {
      return
    }
    request.cancelAllRequest()
  })
}

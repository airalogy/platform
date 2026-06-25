import type { Router } from "vue-router"
import { getUserInfoById } from "@/service/api/users"

export function createDocumentTitleGuard(router: Router) {
  router.afterEach(() => {
    getUserInfoById.clear()
  })
}

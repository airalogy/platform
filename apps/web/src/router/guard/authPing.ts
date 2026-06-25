import type { Router } from "vue-router"
import { getUserAPIKey } from "@/service/api/auth"
import { localStg } from "@/utils/storage"

const PING_COOLDOWN_MS = 5000
let lastPingAt = 0
let lastPingPath = ""
let isPinging = false

export function createAuthPingGuard(router: Router) {
  router.afterEach((to) => {
    if (!localStg.get("token")) {
      return
    }

    const authRouteNames = new Set(["login", "sign-up", "forget-password"])
    if (authRouteNames.has(String(to.name))) {
      return
    }

    if (isPinging) {
      return
    }

    const now = Date.now()
    if (to.fullPath === lastPingPath && now - lastPingAt < PING_COOLDOWN_MS) {
      return
    }

    lastPingAt = now
    lastPingPath = to.fullPath
    isPinging = true

    void getUserAPIKey().finally(() => {
      isPinging = false
    })
  })
}

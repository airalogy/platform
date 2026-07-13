import type { Router } from "vue-router"
import { useInstanceStore } from "@/store/modules/instance"
import { localStg } from "@/utils/storage"

const SINGLE_LAB_REDIRECT_ROUTES = new Set([
  "home",
  "labs",
  "labs-my",
  "labs-public",
  "lab-group-projects",
  "lab-group-members",
  "lab-group-settings",
])

export function createInstanceGuard(router: Router) {
  router.beforeEach((to, _from, next) => {
    const instanceStore = useInstanceStore()
    if (!instanceStore.loaded || !instanceStore.isSingleLab) {
      next()
      return
    }

    const routeName = String(to.name || "")
    const isLogin = Boolean(localStg.get("token"))
    if (!instanceStore.initialized) {
      if (routeName === "instance-setup") {
        next()
      }
      else {
        next({ name: "instance-setup", replace: true })
      }
      return
    }

    if (routeName === "instance-setup") {
      next({ name: isLogin ? "home" : "login", replace: true })
      return
    }

    if (
      routeName === "sign-up"
      && instanceStore.signupMode !== "open"
      && typeof to.query.inviteToken !== "string"
    ) {
      next({ name: "login", replace: true })
      return
    }

    if (routeName === "root") {
      next({ name: isLogin ? "home" : "login", replace: true })
      return
    }

    const targetsAnotherLab = typeof to.params.labUid === "string"
      && instanceStore.lab
      && to.params.labUid !== instanceStore.lab.uid
    const isUnavailableSurface = to.path.startsWith("/hub")
      || (instanceStore.isStructuredLab && to.path.includes("/groups"))

    if (
      isLogin
      && instanceStore.lab
      && (SINGLE_LAB_REDIRECT_ROUTES.has(routeName) || isUnavailableSurface || targetsAnotherLab)
    ) {
      next({
        name: "lab-projects",
        params: { labUid: instanceStore.lab.uid },
        replace: true,
      })
      return
    }

    next()
  })
}

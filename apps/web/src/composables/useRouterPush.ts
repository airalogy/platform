import type { ExceptionNameKey, RouteNameKey } from "@/types/page-route"
import type { LocationQueryValue, RouteLocationRaw } from "vue-router"
import { router as globalRouter } from "@/router"
import { useInstanceStore } from "@/store/modules/instance"
import { useRouter } from "vue-router"

export interface RouterPushOptions {
  query?: Record<string, string>
  params?: Record<string, string>
}

/**
 * Router push
 *
 * Jump to the specified route, it can replace function router.push
 *
 * @param inSetup Whether is in vue script setup
 */
export function useRouterPush(inSetup = true) {
  const router = inSetup ? useRouter() : globalRouter
  const route = globalRouter.currentRoute
  const instanceStore = useInstanceStore()

  const routerPush = router.push

  const routerBack = router.back

  const routerReplace = router.replace

  function routerPushByKey(key: RouteNameKey, options?: RouterPushOptions) {
    const { query, params } = options || {}

    const routeLocation: RouteLocationRaw = {
      name: key,
    }

    if (query) {
      routeLocation.query = query
    }

    if (params) {
      routeLocation.params = params
    }

    return routerPush(routeLocation)
  }

  async function toRoot() {
    return routerPushByKey("root")
  }

  async function toHome() {
    if (instanceStore.isSingleLab && instanceStore.lab) {
      return routerPushByKey("lab-projects", {
        params: { labUid: instanceStore.lab.uid },
      })
    }
    return routerPushByKey("home")
  }

  async function toNotFound(source?: "protocol" | "lab" | "project") {
    let routeName: ExceptionNameKey = "not-found"
    switch (source) {
      case "protocol":
        routeName = "protocol-not-found"
        break
      case "lab":
        routeName = "lab-not-found"
        break
      case "project":
        routeName = "project-not-found"
        break
    }
    return routerPushByKey(routeName)
  }

  function routerReplaceByKey(routeName: RouteNameKey, options?: RouterPushOptions) {
    return routerReplace({
      name: routeName,
      ...options,
    })
  }
  /**
   * Navigate to login page
   *
   * @param loginModule The login module
   * @param redirectUrl The redirect url, if not specified, it will be the current route fullPath
   */
  async function toLogin(loginModule?: string, redirectUrl?: string) {
    const module = loginModule || "email-login"

    const options: RouterPushOptions = {
      params: {
        module,
      },
    }

    const redirect = redirectUrl || route.value.fullPath

    options.query = {
      redirect,
    }

    return routerPushByKey("login", options)
  }

  /**
   * Toggle login module
   *
   * @param module
   */
  async function toggleLoginModule(module: string) {
    const query = route.value.query as Record<string, string>

    return routerPushByKey("login", { query, params: { module } })
  }

  /** Redirect from login */
  async function redirectFromLogin() {
    const { query, matched } = route.value || {}
    const redirect = (query?.redirect ?? null) as LocationQueryValue

    if (redirect) {
      await routerPush(redirect)
    }
    else {
      await toHome()
    }
  }

  return {
    route,
    router,
    routerPush,
    routerBack,
    routerPushByKey,
    routerReplace,
    routerReplaceByKey,
    toLogin,
    toRoot,
    toHome,
    toNotFound,
    toggleLoginModule,
    redirectFromLogin,
  }
}

import type { RouteRecordRaw } from "vue-router"
import { SetupStoreId } from "@/enum"
import { router } from "@/router"

import { createRoutes } from "@/router/routes"
import { getHomeBreadcrumb } from "@/utils/breadcrumb/constants"
import { defineStore } from "pinia"

import { computed, ref } from "vue"

import { useAppStore } from "../app"
import { useAuthStore } from "../auth"
import {
  filterAuthRoutesByRoles,
  getBreadcrumbsByRoute,
  getCacheRouteNames,
  getGlobalMenusByAuthRoutes,
  isRouteExistByRouteName,
  sortRoutesByOrder,
  transformMenuToBreadcrumb,
  updateLocaleOfGlobalMenus,
} from "./shared"

export const useRouteStore = defineStore(SetupStoreId.ROUTE, () => {
  const appStore = useAppStore()
  const authStore = useAuthStore()

  /** Global menus */
  const menus = ref<App.Global.Menu[]>([])
  const removeRouteFns: (() => void)[] = []

  /** Home menus */
  const homeBreadcrumb = computed(() => {
    const options: App.Global.Breadcrumb[] = menus.value
      .filter(({ routePath, label }) => Boolean(label) && routePath !== "/home")
      .map((it) => {
        const option = transformMenuToBreadcrumb(it)
        let result = option
        if (option.options) {
          result = option.options.find(item => item.routePath === "") || option
          result.label = option.breadcrumbLabel || option.label
        }
        else {
          result.label = result.breadcrumbLabel || "Breadcrumb"
        }

        return result
      })

    return { ...getHomeBreadcrumb(), options } as App.Global.Breadcrumb
  })

  const breadcrumbs = computed(() => {
    const currentBreadcrumb = getBreadcrumbsByRoute(router.currentRoute.value, menus.value)

    return [homeBreadcrumb.value, ...currentBreadcrumb]
  })

  const isInitAuthRoute = ref(false)
  const setIsInitAuthRoute = (val: boolean) => (isInitAuthRoute.value = val)
  /** Cache routes */
  const cacheRoutes = ref<string[]>([])

  /**
   * Get cache routes
   *
   * @param routes Vue routes
   */
  function getCacheRoutes(routes: RouteRecordRaw[]) {
    const { constantRoutes } = createRoutes()

    cacheRoutes.value = getCacheRouteNames([...constantRoutes, ...routes]) as string[]
  }

  /**
   * Add cache routes
   *
   * @param routeKey
   */
  function addCacheRoutes(routeKey: App.Global.RouteKey) {
    if (cacheRoutes.value.includes(routeKey))
      return

    cacheRoutes.value.push(routeKey)
  }

  /**
   * Remove cache routes
   *
   * @param routeKey
   */
  function removeCacheRoutes(routeKey: App.Global.RouteKey) {
    const index = cacheRoutes.value.findIndex(item => item === routeKey)

    if (index === -1)
      return

    cacheRoutes.value.splice(index, 1)
  }

  /**
   * Re-cache routes by route key
   *
   * @param routeKey
   */
  async function reCacheRoutesByKey(routeKey: App.Global.RouteKey) {
    removeCacheRoutes(routeKey)

    await appStore.reloadPage()

    addCacheRoutes(routeKey)
  }

  /**
   * Re-cache routes by route keys
   *
   * @param routeKeys
   */
  async function reCacheRoutesByKeys(routeKeys: App.Global.RouteKey[]) {
    for await (const key of routeKeys) {
      await reCacheRoutesByKey(key)
    }
  }
  /** Init auth route */
  function initAuthRoute() {
    initStaticAuthRoute()
  }

  /** Init static auth route */
  function initStaticAuthRoute() {
    const { authRoutes } = createRoutes()

    const filteredAuthRoutes = filterAuthRoutesByRoles(authRoutes, authStore.userInfo.roles || [])
    handleAuthRoutes(filteredAuthRoutes)

    setIsInitAuthRoute(true)
  }
  /**
   * Handle routes
   *
   * @param routes Auth routes
   */
  function handleAuthRoutes(routes: RouteRecordRaw[]) {
    const sortRoutes = sortRoutesByOrder(routes)

    addRoutesToVueRouter(sortRoutes)

    getGlobalMenus(sortRoutes)

    getCacheRoutes(sortRoutes)
  }

  /**
   * Get cache routes
   *
   * @param routes Vue routes
   */
  // function getCacheRoutes(routes: RouteRecordRaw[]) {
  //   const { constantRoutes } = createRoutes()

  //   cacheRoutes.value = getCacheRouteNames([...constantRoutes, ...routes])
  // }

  /**
   * Add routes to vue router
   *
   * @param routes Vue routes
   */
  function addRoutesToVueRouter(routes: RouteRecordRaw[]) {
    routes.forEach((route) => {
      const removeFn = router.addRoute(route)
      addRemoveRouteFn(removeFn)
    })
  }
  /**
   * Add remove route fn
   *
   * @param fn
   */
  function addRemoveRouteFn(fn: () => void) {
    removeRouteFns.push(fn)
  }

  /** Get global menus */
  function getGlobalMenus(routes: RouteRecordRaw[]) {
    menus.value = getGlobalMenusByAuthRoutes(routes)
  }

  /**
   * Get is auth route exist
   *
   * @param routePath Route path
   */
  function getIsAuthRouteExist(routeName: string) {
    if (!routeName) {
      return false
    }

    const { authRoutes } = createRoutes()

    return isRouteExistByRouteName(routeName, authRoutes)
  }

  /** Reset store */
  function resetStore() {
    const routeStore = useRouteStore()

    routeStore.$reset()

    resetVueRoutes()
  }
  /** Reset vue routes */
  function resetVueRoutes() {
    removeRouteFns.forEach(fn => fn())
    removeRouteFns.length = 0
  }

  /** Update global menus by locale */
  function updateGlobalMenusByLocale() {
    menus.value = updateLocaleOfGlobalMenus(menus.value)
  }

  const dynamicBreadcrumbs = ref<App.Global.Breadcrumb[]>([])

  function setDynamicBreadcrumbs(val: App.Global.Breadcrumb | App.Global.Breadcrumb[]) {
    if (Array.isArray(val)) {
      dynamicBreadcrumbs.value = val
    }
    else {
      dynamicBreadcrumbs.value = [val]
    }
  }

  function addDynamicBreadcrumbs(val: App.Global.Breadcrumb | App.Global.Breadcrumb[]) {
    if (Array.isArray(dynamicBreadcrumbs.value)) {
      if (Array.isArray(val)) {
        dynamicBreadcrumbs.value.push(...val)
      }
      else {
        dynamicBreadcrumbs.value.push(val)
      }
    }
    else {
      setDynamicBreadcrumbs(val)
    }
  }

  function clearDynamicBreadcrumbs() {
    dynamicBreadcrumbs.value = []
  }

  return {
    menus,
    homeBreadcrumb,
    breadcrumbs,
    initStaticAuthRoute,
    handleAuthRoutes,
    addRoutesToVueRouter,
    addRemoveRouteFn,
    getGlobalMenus,
    getIsAuthRouteExist,
    isInitAuthRoute,
    setIsInitAuthRoute,
    initAuthRoute,
    resetStore,
    cacheRoutes,
    reCacheRoutesByKey,
    reCacheRoutesByKeys,
    updateGlobalMenusByLocale,
    addCacheRoutes,
    removeCacheRoutes,
    dynamicBreadcrumbs,
    setDynamicBreadcrumbs,
    addDynamicBreadcrumbs,
    clearDynamicBreadcrumbs,
  }
})

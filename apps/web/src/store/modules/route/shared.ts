import type {
  RouteLocationNormalizedLoaded,
  RouteRecordName,
  RouteRecordRaw,
} from "vue-router"
import { $t } from "@airalogy/shared/locales"

/**
 * Filter auth routes by roles
 *
 * @param routes Auth routes
 * @param roles Roles
 */
export function filterAuthRoutesByRoles(routes: RouteRecordRaw[], roles: string[]) {
  const SUPER_ROLE = "R_SUPER"

  // if the user is super admin, then it is allowed to access all routes
  if (roles.includes(SUPER_ROLE)) {
    return routes
  }

  return routes.flatMap(route => filterAuthRouteByRoles(route, roles))
}

/**
 * Filter auth route by roles
 *
 * @param route Auth route
 * @param roles Roles
 */
function filterAuthRouteByRoles(route: RouteRecordRaw, roles: string[]) {
  const routeRoles = (route.meta && (route.meta.roles as string[])) || []

  // if the route's "roles" is empty, then it is allowed to access
  if (!routeRoles.length) {
    return [route]
  }

  // if the user's role is included in the route's "roles", then it is allowed to access
  const hasPermission = routeRoles.some(role => roles.includes(role))

  const filterRoute = { ...route }

  if (filterRoute.children?.length) {
    filterRoute.children = filterRoute.children.flatMap(item => filterAuthRouteByRoles(item, roles))
  }

  return hasPermission ? [filterRoute] : []
}

/**
 * sort route by order
 *
 * @param route route
 */
function sortRouteByOrder(route: RouteRecordRaw) {
  if (route.children?.length) {
    route.children.sort(
      (next, prev) => (Number(next.meta?.order) || 0) - (Number(prev.meta?.order) || 0),
    )
    route.children.forEach(sortRouteByOrder)
  }

  return route
}

/**
 * sort routes by order
 *
 * @param routes routes
 */
export function sortRoutesByOrder(routes: RouteRecordRaw[]) {
  routes.sort((next, prev) => (Number(next.meta?.order) || 0) - (Number(prev.meta?.order) || 0))
  routes.forEach(sortRouteByOrder)

  return routes
}

/**
 * Get global menus by auth routes
 *
 * @param routes Auth routes
 */
export function getGlobalMenusByAuthRoutes(routes: RouteRecordRaw[]) {
  const menus: App.Global.Menu[] = []

  routes.forEach((route) => {
    if (route.meta?.hideInMenu) {
      return
    }

    const menu = getGlobalMenuByBaseRoute(route)

    if (!menu) {
      return
    }

    if (route.children?.length) {
      menu.children = getGlobalMenusByAuthRoutes(route.children)
    }

    menus.push(menu)
  })

  return menus
}

/**
 * Update locale of global menus
 *
 * @param menus
 */

export function updateLocaleOfGlobalMenus(menus: App.Global.Menu[]) {
  const result: App.Global.Menu[] = []

  menus.forEach((menu) => {
    const { i18nKey, label, children, breadcrumbI18nKey } = menu

    const newLabel = i18nKey ? $t(i18nKey) : label

    const newMenu: App.Global.Menu = {
      ...menu,
      label: newLabel,
      breadcrumbLabel: breadcrumbI18nKey ? $t(breadcrumbI18nKey) : newLabel,
    }

    if (children?.length) {
      newMenu.children = updateLocaleOfGlobalMenus(children)
    }

    result.push(newMenu)
  })

  return result
}

/**
 * Get global menu by route
 *
 * @param route
 */
function getGlobalMenuByBaseRoute(route: RouteLocationNormalizedLoaded | RouteRecordRaw) {
  const { name, path } = route
  const { title, i18nKey, breadcrumbI18nKey, topLevel, hideInMenu = false, hideInBreadcrumb = false } = route.meta ?? {}

  if (topLevel === false) {
    return
  }

  const label = i18nKey ? $t(i18nKey) : title!

  const menu: App.Global.Menu = {
    key: name as string,
    label,
    i18nKey,
    breadcrumbI18nKey,
    breadcrumbLabel: breadcrumbI18nKey ? $t(breadcrumbI18nKey) : label,
    routeKey: name as App.Global.RouteKey,
    routePath: path,
    meta: {
      hideInMenu,
      hideInBreadcrumb,
    },
  }

  return menu
}

/**
 * Get cache route names
 *
 * @param routes Vue routes (two levels)
 */
export function getCacheRouteNames(routes: RouteRecordRaw[]) {
  const cacheNames: RouteRecordName[] = []

  routes.forEach((route) => {
    // only get last two level route, which has component
    route.children?.forEach((child) => {
      if (child.component && child.meta?.keepAlive && child.name) {
        cacheNames.push(child.name)
      }
    })
  })

  return cacheNames
}

/**
 * Is route exist by route name
 *
 * @param routeName
 * @param routes
 */
export function isRouteExistByRouteName(routeName: string, routes: RouteRecordRaw[]) {
  return routes.some(route => recursiveGetIsRouteExistByRouteName(route, routeName))
}

/**
 * Recursive get is route exist by route name
 *
 * @param route
 * @param routeName
 */
function recursiveGetIsRouteExistByRouteName(route: RouteRecordRaw, routeName: string) {
  let isExist = route.name === routeName

  if (isExist) {
    return true
  }

  if (route.children && route.children.length) {
    isExist = route.children.some(item => recursiveGetIsRouteExistByRouteName(item, routeName))
  }

  return isExist
}

/**
 * Get selected menu key path
 *
 * @param selectedKey
 * @param menus
 */
export function getSelectedMenuKeyPathByKey(selectedKey: string, menus: App.Global.Menu[]) {
  const keyPath: string[] = []

  menus.some((menu) => {
    const path = findMenuPath(selectedKey, menu)

    const find = Boolean(path?.length)

    if (find) {
      keyPath.push(...path!)
    }

    return find
  })

  return keyPath
}

/**
 * Find menu path
 *
 * @param targetKey Target menu key
 * @param menu Menu
 */
function findMenuPath(targetKey: string, menu: App.Global.Menu): string[] | null {
  const path: string[] = []

  function dfs(item: App.Global.Menu): boolean {
    path.push(item.key)

    if (item.key === targetKey) {
      return true
    }

    if (item.children) {
      for (const child of item.children) {
        if (dfs(child)) {
          return true
        }
      }
    }

    path.pop()

    return false
  }

  if (dfs(menu)) {
    return path
  }

  return null
}

/**
 * Transform menu to breadcrumb
 *
 * @param menu
 */
export function transformMenuToBreadcrumb(menu: App.Global.Menu) {
  const { children, ...rest } = menu

  const breadcrumb: App.Global.Breadcrumb = {
    ...rest,
  }

  if (children?.length) {
    const options = children.filter(it => !it.meta?.hideInMenu && !it.meta?.hideInBreadcrumb).map(transformMenuToBreadcrumb)
    if (options.length) {
      breadcrumb.options = options
    }
  }

  return breadcrumb
}

/**
 * Get breadcrumbs by route
 *
 * @param route
 * @param menus
 */
export function getBreadcrumbsByRoute(
  route: RouteLocationNormalizedLoaded,
  menus: App.Global.Menu[],
): App.Global.Breadcrumb[] {
  const key = route.name as string
  const activeKey = route.meta?.activeMenu

  const menuKey = activeKey || key

  for (const menu of menus) {
    if (menu.key === menuKey) {
      const breadcrumbMenu = menuKey !== activeKey ? menu : getGlobalMenuByBaseRoute(route)
      if (breadcrumbMenu && !breadcrumbMenu.meta?.hideInBreadcrumb) {
        return [transformMenuToBreadcrumb(breadcrumbMenu)]
      }
    }

    if (menu.children?.length) {
      const result = getBreadcrumbsByRoute(route, menu.children)
      if (result.length) {
        return [transformMenuToBreadcrumb(menu), ...result]
      }
    }
  }

  return []
}

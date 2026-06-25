import type { NavigationGuardNext, RouteLocationNormalized, Router } from "vue-router"
import { useAuthStore } from "@/store/modules/auth"
import { useRouteStore } from "@/store/modules/route"
import { localStg } from "@/utils/storage"

const SUPER_ADMIN = "R_SUPER"
const ADMIN = "R_ADMIN"

function isGuestAccessibleRoute(to: RouteLocationNormalized) {
  return Boolean(to.meta.constant || to.meta.allowGuest)
}

export function createPermissionGuard(router: Router) {
  router.beforeEach(async (to, from, next) => {
    const pass = createAuthRouteGuard(to, from, next)

    if (!pass)
      return

    // 1. route with href
    if (to.meta.href) {
      window.open(to.meta.href, "_blank")
      next({ path: from.fullPath, replace: true, query: from.query, hash: to.hash })
    }

    const authStore = useAuthStore()

    const isLogin = Boolean(localStg.get("token"))

    const needLogin = !isGuestAccessibleRoute(to)
    const routeRoles = to.meta.roles || []
    const rootRoute = "root"
    const homeRoute = "home"
    const loginRoute = "login"
    const signupRoute = "sign-up"
    const noPermissionRoute = "403"

    // check whether the user has permission to access the route
    // 1. if the route's "roles" is empty, then it is allowed to access
    // 2. if the user is super admin, then it is allowed to access
    // 3. if the user's role is included in the route's "roles", then it is allowed to access

    // Permission check with admin route handling
    const isAdminRoute = to.path.startsWith("/admin")

    // Check if user has required permissions
    let hasPermission = false

    if (!routeRoles.length && !isAdminRoute) {
      // Route with no role restrictions and not admin route
      hasPermission = true
    }
    else if (isAdminRoute) {
      // Admin routes require admin permissions
      hasPermission = Boolean(authStore.userInfo.roles
        && (authStore.userInfo.roles.includes(SUPER_ADMIN) || authStore.userInfo.roles.includes(ADMIN)))
    }
    else {
      // Regular role-based permission check
      hasPermission = Boolean(authStore.userInfo.roles
        && (authStore.userInfo.roles.includes(SUPER_ADMIN)
          || authStore.userInfo.roles.some(role => routeRoles.includes(role))))
    }

    const strategicPatterns = [
      // 1. if it is login route when logged in, change to the home page
      {
        condition: isLogin && (to.name === loginRoute || to.name === signupRoute),
        callback: () => {
          next({ name: homeRoute })
        },
      },
      // 2. if it is root route when logged in, change to the home page
      {
        condition: isLogin && to.name === rootRoute,
        callback: () => {
          next({ name: homeRoute })
        },
      },
      // 3. if is is constant route, then it is allowed to access directly
      {
        condition: !needLogin,
        callback: () => {
          next()
        },
      },
      // 4. if the route need login but the user is not logged in, then switch to the login page
      {
        condition: !isLogin && needLogin,
        callback: () => {
          next({ name: loginRoute, query: { redirect: to.fullPath } })
        },
      },
      // 5. if the user is logged in and has permission, then it is allowed to access
      {
        condition: isLogin && needLogin && hasPermission,
        callback: () => {
          next()
        },
      },
      // 6. if the user is logged in but does not have permission, then switch to the 403 page
      {
        condition: isLogin && needLogin && !hasPermission,
        callback: () => {
          next({ name: noPermissionRoute })
        },
      },
      // 7. if it's an admin route but user is not logged in, redirect to login with admin context
      {
        condition: !isLogin && isAdminRoute,
        callback: () => {
          next({ name: loginRoute, query: { redirect: to.fullPath, type: "admin" } })
        },
      },
    ]

    strategicPatterns.some(({ condition, callback }) => {
      if (condition) {
        callback()
      }

      return condition
    })
  })
}
function createAuthRouteGuard(
  to: RouteLocationNormalized,
  _from: RouteLocationNormalized,
  next: NavigationGuardNext,
) {
  const notFoundRoute: string = "not-found"
  const isNotFoundRoute = to.name === notFoundRoute
  const rootRoute = "root"

  // 1. If the route is the constant route but is not the "not-found" route, then it is allowed to access.
  if (isGuestAccessibleRoute(to) && !isNotFoundRoute && to.name !== rootRoute) {
    return true
  }

  // 2. If the auth route is initialized but is not the "not-found" route, then it is allowed to access.
  const routeStore = useRouteStore()
  if (routeStore.isInitAuthRoute && !isNotFoundRoute) {
    return true
  }

  // 3. If the route is initialized, check whether the route exists.
  if (routeStore.isInitAuthRoute && isNotFoundRoute) {
    const exist = routeStore.getIsAuthRouteExist(to.path)

    if (exist) {
      const noPermissionRoute = "403"

      next({ name: noPermissionRoute })

      return false
    }

    return true
  }

  // 4. If the user is not logged in, then redirect to the login page.
  // TODO: mock login
  const isLogin = Boolean(localStg.get("token"))

  if (!isLogin) {
    if (to.name === rootRoute) {
      routeStore.initAuthRoute()
      next()
      return false
    }

    const loginRoute = "login"
    const redirect = to.fullPath

    next({ name: loginRoute, query: { redirect } })

    return false
  }

  // 5. init auth route
  routeStore.initAuthRoute()

  // 6. the route is caught by the "not-found" route because the auto route is not initialized. after the auto route is initialized, redirect to the original route.
  if (isNotFoundRoute) {
    const path = to.redirectedFrom?.name === rootRoute ? "/" : to.fullPath

    next({ path, replace: true, query: to.query, hash: to.hash })

    return false
  }

  return true
}

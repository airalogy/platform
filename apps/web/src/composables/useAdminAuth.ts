import { useAuthStore } from "@/store/modules/auth"
import { useMessage } from "naive-ui"
import { computed } from "vue"
import { useRouter } from "vue-router"

/**
 * Admin authentication and authorization composable
 */
export function useAdminAuth() {
  const authStore = useAuthStore()
  const router = useRouter()
  const message = useMessage()

  // Admin role constants
  const ADMIN_ROLES = {
    SUPER: "R_SUPER",
    ADMIN: "R_ADMIN",
  } as const

  // Check if user has any admin role
  const isAdmin = computed(() => {
    const userRoles = authStore.userInfo.roles || []
    return userRoles.includes(ADMIN_ROLES.SUPER) || userRoles.includes(ADMIN_ROLES.ADMIN)
  })

  // Check if user is super admin
  const isSuperAdmin = computed(() => {
    const userRoles = authStore.userInfo.roles || []
    return userRoles.includes(ADMIN_ROLES.SUPER)
  })

  // Check if user has specific admin role
  function hasAdminRole(role: string): boolean {
    const userRoles = authStore.userInfo.roles || []
    return userRoles.includes(role) || userRoles.includes(ADMIN_ROLES.SUPER)
  }

  // Check if user can access admin route
  function canAccessAdminRoute(requiredRoles?: string[]): boolean {
    if (!isAdmin.value)
      return false

    if (!requiredRoles || requiredRoles.length === 0) {
      return isAdmin.value
    }

    const userRoles = authStore.userInfo.roles || []

    // Super admin can access everything
    if (userRoles.includes(ADMIN_ROLES.SUPER))
      return true

    // Check if user has any of the required roles
    return requiredRoles.some(role => userRoles.includes(role))
  }

  // Redirect to admin login if not authenticated
  async function requireAdminAuth(requiredRoles?: string[]) {
    if (!authStore.isLogin) {
      message.warning("Please login to access admin panel")
      await router.push({
        name: "login",
        query: { redirect: router.currentRoute.value.fullPath, type: "admin" },
      })
      return false
    }

    if (!canAccessAdminRoute(requiredRoles)) {
      message.error("You don't have permission to access this admin area")
      await router.push({ name: "403" })
      return false
    }

    return true
  }

  // Get admin user info
  const adminUserInfo = computed(() => {
    if (!isAdmin.value)
      return null

    return {
      ...authStore.userInfo,
      adminLevel: isSuperAdmin.value ? "super" : "admin",
      permissions: authStore.userInfo.roles || [],
    }
  })

  // Admin navigation guard
  function createAdminGuard(requiredRoles?: string[]) {
    return async () => {
      return await requireAdminAuth(requiredRoles)
    }
  }

  // Check specific admin permissions
  function hasAdminPermission(permission: string): boolean {
    // Define permission mappings
    const permissionMap: Record<string, string[]> = {
      // User management permissions
      "users.read": [ADMIN_ROLES.ADMIN, ADMIN_ROLES.SUPER],
      "users.write": [ADMIN_ROLES.SUPER],
      "users.delete": [ADMIN_ROLES.SUPER],

      // Content management permissions
      "content.read": [ADMIN_ROLES.ADMIN, ADMIN_ROLES.SUPER],
      "content.write": [ADMIN_ROLES.ADMIN, ADMIN_ROLES.SUPER],
      "content.delete": [ADMIN_ROLES.SUPER],

      // System management permissions
      "system.read": [ADMIN_ROLES.SUPER],
      "system.write": [ADMIN_ROLES.SUPER],
      "system.logs": [ADMIN_ROLES.SUPER],
      "system.monitoring": [ADMIN_ROLES.SUPER],
    }

    const requiredRoles = permissionMap[permission]
    if (!requiredRoles)
      return false

    return canAccessAdminRoute(requiredRoles)
  }

  // Get available admin menu items based on permissions
  const availableAdminMenus = computed(() => {
    const menus = []

    // Dashboard - available to all admins
    if (isAdmin.value) {
      menus.push({
        key: "dashboard",
        label: "Dashboard",
        children: ["admin-overview", "admin-analytics"],
      })
    }

    // User management - different levels for different roles
    if (hasAdminPermission("users.read")) {
      const userMenus = ["admin-users-list"]

      if (hasAdminPermission("users.write")) {
        userMenus.push("admin-user-roles", "admin-permissions")
      }

      menus.push({
        key: "users",
        label: "User Management",
        children: userMenus,
      })
    }

    // Content management
    if (hasAdminPermission("content.read")) {
      menus.push({
        key: "content",
        label: "Content Management",
        children: ["admin-labs", "admin-projects", "admin-protocols"],
      })
    }

    // System management - super admin only
    if (hasAdminPermission("system.read")) {
      menus.push({
        key: "system",
        label: "System",
        children: ["admin-settings", "admin-logs", "admin-monitoring"],
      })
    }

    return menus
  })

  return {
    // Computed properties
    isAdmin,
    isSuperAdmin,
    adminUserInfo,
    availableAdminMenus,

    // Methods
    hasAdminRole,
    canAccessAdminRoute,
    requireAdminAuth,
    createAdminGuard,
    hasAdminPermission,

    // Constants
    ADMIN_ROLES,
  }
}

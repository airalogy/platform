import type { CustomRoute } from "#/page-route"

export const adminRoutes: CustomRoute[] = [
  {
    path: "/admin",
    name: "admin",
    redirect: "/admin/dashboard",
    component: () => import("@/layouts/admin-layout/index.vue"),
    meta: {
      title: "Admin Panel",
      roles: ["R_ADMIN", "R_SUPER"],
      requiresAuth: true,
      hideInMenu: true,
      notContainer: true,
    },
    children: [
      // Dashboard
      {
        path: "dashboard",
        name: "admin-dashboard",
        redirect: "/admin/dashboard/overview",
        meta: {
          title: "Dashboard",
          roles: ["R_ADMIN", "R_SUPER"],
        },
        children: [
          {
            path: "overview",
            name: "admin-overview",
            component: () => import("@/views/admin/dashboard/overview.vue"),
            meta: {
              title: "Overview",
              roles: ["R_ADMIN", "R_SUPER"],
            },
          },
          {
            path: "analytics",
            name: "admin-analytics",
            component: () => import("@/views/admin/dashboard/analytics.vue"),
            meta: {
              title: "Analytics",
              roles: ["R_ADMIN", "R_SUPER"],
            },
          },
        ],
      },

      // User Management
      {
        path: "users",
        name: "admin-users",
        redirect: "/admin/users/list",
        meta: {
          title: "User Management",
          roles: ["R_ADMIN", "R_SUPER"],
        },
        children: [
          {
            path: "list",
            name: "admin-users-list",
            component: () => import("@/views/admin/users/list.vue"),
            meta: {
              title: "All Users",
              roles: ["R_ADMIN", "R_SUPER"],
            },
          },
          {
            path: "roles",
            name: "admin-user-roles",
            component: () => import("@/views/admin/users/roles.vue"),
            meta: {
              title: "User Roles",
              roles: ["R_SUPER"], // Only super admin can manage roles
            },
          },
          {
            path: "permissions",
            name: "admin-permissions",
            component: () => import("@/views/admin/users/permissions.vue"),
            meta: {
              title: "Permissions",
              roles: ["R_SUPER"], // Only super admin can manage permissions
            },
          },
        ],
      },

      // Content Management
      {
        path: "content",
        name: "admin-content",
        redirect: "/admin/content/labs",
        meta: {
          title: "Content Management",
          roles: ["R_ADMIN", "R_SUPER"],
        },
        children: [
          {
            path: "labs",
            name: "admin-labs",
            component: () => import("@/views/admin/content/labs.vue"),
            meta: {
              title: "Labs",
              roles: ["R_ADMIN", "R_SUPER"],
            },
          },
          {
            path: "projects",
            name: "admin-projects",
            component: () => import("@/views/admin/content/projects.vue"),
            meta: {
              title: "Projects",
              roles: ["R_ADMIN", "R_SUPER"],
            },
          },
          {
            path: "protocols",
            name: "admin-protocols",
            component: () => import("@/views/admin/content/protocols.vue"),
            meta: {
              title: "Protocols",
              roles: ["R_ADMIN", "R_SUPER"],
            },
          },
        ],
      },

      // System Management
      {
        path: "system",
        name: "admin-system",
        redirect: "/admin/system/settings",
        meta: {
          title: "System",
          roles: ["R_SUPER"], // Only super admin for system management
        },
        children: [
          {
            path: "settings",
            name: "admin-settings",
            component: () => import("@/views/admin/system/settings.vue"),
            meta: {
              title: "Settings",
              roles: ["R_SUPER"],
            },
          },
          {
            path: "logs",
            name: "admin-logs",
            component: () => import("@/views/admin/system/logs.vue"),
            meta: {
              title: "Logs",
              roles: ["R_SUPER"],
            },
          },
          {
            path: "monitoring",
            name: "admin-monitoring",
            component: () => import("@/views/admin/system/monitoring.vue"),
            meta: {
              title: "Monitoring",
              roles: ["R_SUPER"],
            },
          },
        ],
      },
    ],
  },
]

import type { CustomRoute, ProtocolNameKey } from "#/page-route"

export const protocolRoute: CustomRoute<ProtocolNameKey> = {
  path: "/protocols",
  name: "protocols",
  redirect: "/protocols/my",
  component: () => import("@/views/project-protocols/layout.vue"),
  meta: {
    title: "Protocols",
    requiresAuth: true,
  },
  children: [
    {
      path: "my",
      name: "protocols-my",
      component: () => import("@/views/project-protocols/my.vue"),
      meta: {
        title: "My Protocols",
        requiresAuth: true,
      },
    },
  ],
}

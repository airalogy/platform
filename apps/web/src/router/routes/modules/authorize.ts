import type { AuthorizeNameKey, CustomRoute } from "#/page-route"

export const authorizeRoute: CustomRoute<AuthorizeNameKey> = {
  path: "/authorize",
  name: "authorize",
  meta: { title: "Authorize" },
  component: () => import("@/views/authorize/index.vue"),
}

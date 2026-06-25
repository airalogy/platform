import type { CustomRoute, RootNameKey } from "#/page-route"
import GlobalLayout from "@/layouts/global-layout/index.vue"

export const ROOT_ROUTE: CustomRoute<RootNameKey> = {
  path: "/",
  component: GlobalLayout,
  meta: {
    title: "root",
    i18nKey: "common.index",
    constant: true,
  },
  children: [
    {
      path: "",
      name: "root",
      component: () => import("@/views/root/index.vue"),
    },
  ],
}

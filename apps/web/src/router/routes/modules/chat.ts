import type { CustomRoute } from "#/page-route"
import GlobalLayout from "@/layouts/global-layout/index.vue"

export const chatRoute: CustomRoute = {
  meta: {
    title: "Aira Chat",
    hideInBreadcrumb: true,
    constant: false,
    hideFooter: true,
    notContainer: true,
    scrollMode: "wrapper",
    layoutFullHeight: true,
  },
  path: "/chat",
  component: GlobalLayout,
  children: [
    {
      meta: {
        title: "Aira Chat",
        hideInBreadcrumb: true,
        constant: false,
        hideFooter: true,
        notContainer: true,
        scrollMode: "wrapper",
        layoutFullHeight: true,
      },
      path: "",
      name: "global-chat",
      component: () => import("@/views/chat/index.vue"),
    },
  ],
}

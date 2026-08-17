import type { CustomRoute, HelpNameKey } from "#/page-route"
import GlobalLayout from "@/layouts/global-layout/index.vue"

export const helpRoute: CustomRoute<HelpNameKey> = {
  path: "/help",
  component: GlobalLayout,
  meta: {
    title: "Help Center",
    i18nKey: "page.help.title",
    hideInMenu: true,
  },
  children: [
    {
      path: "",
      name: "help-center",
      component: () => import("@/views/help/index.vue"),
      meta: {
        title: "Help Center",
        i18nKey: "page.help.title",
        hideInMenu: true,
      },
    },
  ],
}

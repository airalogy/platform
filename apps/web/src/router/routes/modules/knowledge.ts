import type { CustomRoute, KnowledgeNameKey } from "#/page-route"
import GlobalLayout from "@/layouts/global-layout/index.vue"

export const knowledgeRoute: CustomRoute<KnowledgeNameKey> = {
  path: "/knowledge",
  component: GlobalLayout,
  redirect: { name: "knowledge-home" },
  meta: {
    title: "Knowledge",
    i18nKey: "page.knowledge.title",
    requiresAuth: true,
    hideInMenu: true,
  },
  children: [
    {
      path: "",
      name: "knowledge-home",
      component: () => import("@/views/knowledge/index.vue"),
      meta: {
        title: "Knowledge",
        i18nKey: "page.knowledge.title",
        requiresAuth: true,
        hideInMenu: true,
      },
    },
  ],
}

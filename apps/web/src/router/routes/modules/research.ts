import type { CustomRoute, ResearchNameKey } from "#/page-route"
import GlobalLayout from "@/layouts/global-layout/index.vue"

export const researchRoute: CustomRoute<ResearchNameKey> = {
  path: "/research",
  component: GlobalLayout,
  redirect: { name: "research-tasks" },
  meta: {
    title: "Research",
    i18nKey: "page.research.title",
    requiresAuth: true,
    hideInMenu: true,
  },
  children: [
    {
      path: "tasks",
      name: "research-tasks",
      component: () => import("@/views/research/index.vue"),
      meta: {
        title: "Research Tasks",
        i18nKey: "page.research.title",
        requiresAuth: true,
        hideInMenu: true,
      },
    },
    {
      path: "work-items",
      name: "research-work-items",
      component: () => import("@/views/research/index.vue"),
      meta: {
        title: "My Research Work",
        i18nKey: "page.research.workItems",
        requiresAuth: true,
        hideInMenu: true,
      },
    },
    {
      path: "approvals",
      name: "research-approvals",
      component: () => import("@/views/research/index.vue"),
      meta: {
        title: "My Research Approvals",
        i18nKey: "page.research.approvals",
        requiresAuth: true,
        hideInMenu: true,
      },
    },
    {
      path: "notifications",
      name: "research-notifications",
      component: () => import("@/views/research/index.vue"),
      meta: {
        title: "Research Notifications",
        i18nKey: "page.research.notifications",
        requiresAuth: true,
        hideInMenu: true,
      },
    },
    {
      path: "tasks/:taskId",
      name: "research-task-detail",
      component: () => import("@/views/research/detail.vue"),
      meta: {
        title: "Research Task",
        i18nKey: "page.research.taskDetail",
        requiresAuth: true,
        hideInMenu: true,
      },
    },
  ],
}

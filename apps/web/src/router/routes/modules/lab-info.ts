import type { CustomRoute, LabInfoNameKey } from "#/page-route"

export const labInfoRoute: CustomRoute<LabInfoNameKey> = {
  meta: { i18nKey: "page.labs.info", title: "Labs info", hideInMenu: true },
  path: "/labs/:labUid([\\w-]+)",
  redirect: { name: "lab-projects" },
  component: () => import("@/views/labs/layout.vue"),
  children: [
    {
      path: "projects",
      name: "lab-projects",
      meta: {
        i18nKey: "page.labs.info",
        title: "Lab Projects",
        breadcrumbI18nKey: "breadcrumb.myProjects",
      },
      component: () => import("@/views/labs/projects.vue"),
    },
    {
      path: "records",
      name: "lab-records",
      meta: {
        i18nKey: "page.recordDiary.tab",
        title: "Lab Records",
      },
      component: () => import("@/views/record-diary/index.vue"),
    },
    {
      path: "members",
      name: "lab-members",
      meta: {
        i18nKey: "page.labs.members",
        title: "Lab Members",
        breadcrumbI18nKey: "breadcrumb.allMembers",
      },
      component: () => import("@/views/labs/members.vue"),
    },
    {
      meta: {
        breadcrumbI18nKey: "breadcrumb.groups",
        title: "Lab Groups",
        i18nKey: "page.labs.groups",
      },
      path: "groups",
      name: "lab-groups",
      component: () => import("@/views/labs/groups.vue"),
    },
    {
      path: "organization",
      name: "lab-organization",
      meta: { title: "Lab Organization" },
      component: () => import("@/views/labs/organization.vue"),
    },
    {
      path: "teams",
      name: "lab-teams",
      redirect: { name: "lab-organization" },
      meta: { title: "Lab Organization", hideInMenu: true },
    },
    {
      path: "access",
      name: "lab-access",
      meta: { title: "Lab Access" },
      component: () => import("@/views/labs/access.vue"),
    },
    {
      path: "settings",
      name: "lab-settings",
      component: () => import("@/views/labs/settings.vue"),
    },
  ],
}

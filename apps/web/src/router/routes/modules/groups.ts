import type { CustomRoute, GroupsNameKey } from "#/page-route"

export const groupsRoute: CustomRoute<GroupsNameKey> = {
  meta: { i18nKey: "page.labs.groups", title: "Group info", hideInMenu: true },
  path: "/labs/:labUid([\\w-]+)/groups/:groupId([\\d]+)",
  component: () => import("@/views/group/layout.vue"),
  children: [
    {
      path: "projects",
      name: "lab-group-projects",
      meta: {
        i18nKey: "page.group.projects",
        title: "Group Projects",
        breadcrumbI18nKey: "breadcrumb.myProjects",
      },
      component: () => import("@/views/group/projects.vue"),
    },
    {
      path: "members",
      name: "lab-group-members",
      meta: {
        i18nKey: "page.group.members",
        title: "Group Members",
        breadcrumbI18nKey: "breadcrumb.allMembers",
      },
      component: () => import("@/views/group/members.vue"),
    },
    {
      path: "settings",
      name: "lab-group-settings",
      meta: {
        i18nKey: "page.group.settings",
        title: "Group Settings",
      },
      component: () => import("@/views/group/settings.vue"),
    },
  ],
}

import type { CustomRoute, ProjectInfoNameKey } from "#/page-route"
import type { RouteMeta } from "vue-router"

// Common path pattern for project routes
const PROJECT_PATH = "/labs/:labUid([\\w-]+)/projects/:projectUid([\\w-_]+)"

// Common meta configuration for project routes
function createProjectMeta(title: string, i18nKey: I18n.I18nKey = "page.project.diary"): RouteMeta {
  return {
    i18nKey,
    title,
    hideInMenu: true,
  }
}

export const projectInfoRoute: CustomRoute<ProjectInfoNameKey> = {
  path: PROJECT_PATH,
  meta: { ...createProjectMeta("Project Info", "page.labs.projects"), allowGuest: true },
  redirect: { name: "project-protocols" },
  component: () => import("@/views/project/layout.vue"),
  children: [
    {
      path: "protocols",
      name: "project-protocols",
      meta: { ...createProjectMeta("Project Work Protocols", "page.project.protocols"), allowGuest: true },
      component: () => import("@/views/project/protocols.vue"),
    },
    {
      path: "records",
      name: "project-records",
      meta: { ...createProjectMeta("Project Records", "page.recordDiary.tab"), allowGuest: false },
      component: () => import("@/views/record-diary/index.vue"),
    },
    {
      path: "members",
      name: "project-members",
      meta: { ...createProjectMeta("Project Members", "page.project.members"), allowGuest: false },
      component: () => import("@/views/project/members.vue"),
    },
    {
      path: "settings",
      name: "project-settings",
      meta: { ...createProjectMeta("Project Settings", "page.project.settings"), allowGuest: false },
      component: () => import("@/views/project/settings.vue"),
    },
  ],
}

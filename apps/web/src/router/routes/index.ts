import type { CustomRoute } from "#/page-route"
import { exceptionRoutes } from "./exceptions"
import { authRoute } from "./modules/auth"
import { authorizeRoute } from "./modules/authorize"
import { chatRoute } from "./modules/chat"
import { groupsRoute } from "./modules/groups"
import { homeRoute } from "./modules/home"
import { hubDetailRoute, hubRoute } from "./modules/hub"
import { labInfoRoute } from "./modules/lab-info"
import { labsRoute } from "./modules/labs"
import { userProfileRoute } from "./modules/profile"
import { projectInfoRoute } from "./modules/project-info"
import { projectsRoute } from "./modules/projects"
import { protocolEditorRoute, protocolInfoRoute } from "./modules/protocol-info"
import { protocolRecordRoute } from "./modules/protocol-record"
// import { searchRoute } from "./modules/search"
import { protocolRoute } from "./modules/unit-to-protocol"
import { ROOT_ROUTE } from "./root"

export const customRoutes: CustomRoute[] = [
  ROOT_ROUTE,
  homeRoute,
  authRoute,
  labsRoute,
  labInfoRoute,
  groupsRoute,
  projectsRoute,
  projectInfoRoute,
  protocolRoute,
  protocolInfoRoute,
  protocolEditorRoute,
  {
    path: "/editor",
    component: () => import("@/views/editor/index.vue"),
    meta: { title: "Airalogy Protocol Editor", icon: "edit", hideInMenu: true },
    name: "protocol-editor-playground",
  } as any,
  protocolRecordRoute,
  userProfileRoute,
  authorizeRoute,
  hubRoute,
  hubDetailRoute,
  chatRoute,
  // searchRoute,
  // {
  //   path: "/excel-editor",
  //   name: "excel-editor",
  //   component: () => import("@/components/excel-editor/demo.vue"),
  //   meta: {
  //     title: "Excel Editor",
  //     constant: true,
  //   },
  // },
  // ...adminRoutes,

  ...exceptionRoutes,
]

/** Create routes */
export function createRoutes() {
  const constantRoutes: CustomRoute[] = []
  const authRoutes: CustomRoute[] = []

  customRoutes.forEach((item) => {
    if (item.meta?.constant)
      constantRoutes.push(item)
    else
      authRoutes.push(item)
  })

  return {
    constantRoutes,
    authRoutes,
  }
}

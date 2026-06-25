import type { CustomRoute, HubNameKey } from "#/page-route"
import type { RouteLocationNormalized, RouteLocationRaw } from "vue-router"
import GlobalLayout from "@/layouts/global-layout/index.vue"

function resolveHubDetailRedirect(to: RouteLocationNormalized): RouteLocationRaw {
  const { labUid, projectUid, protocolUid } = to.params as Record<string, string>
  const name: "protocol-records" | "protocol-discussions" | "protocol-detail" = to.name === "hub-detail-record"
    ? "protocol-records"
    : to.name === "hub-detail-discussion"
      ? "protocol-discussions"
      : "protocol-detail"

  return {
    name,
    params: { labUid, projectUid, protocolUid },
    query: to.query,
    hash: to.hash,
  }
}

export const hubRoute: CustomRoute<HubNameKey> = {
  meta: { title: "Hub", allowGuest: true },
  name: "hub",
  path: "/hub",
  redirect: { name: "hub-list" },
  component: GlobalLayout,
  children: [
    {
      path: "list",
      name: "hub-list",
      meta: { title: "All Protocols", breadcrumbI18nKey: "breadcrumb.hubAll", hideInBreadcrumb: true, useSpinWrapper: false, allowGuest: true },
      component: () => import("@/views/hub/protocol-list.vue"),
    },
    {
      path: "search/:section",
      name: "hub-search",
      meta: { title: "Protocol Search", hideInMenu: true, allowGuest: true },
      component: () => import("@/views/hub/protocol-list-search.vue"),
    },
  ],
}

export const hubDetailRoute: CustomRoute<HubNameKey> = {
  meta: { title: "Protocol Detail", hideInMenu: true, hideInBreadcrumb: true, allowGuest: true },
  name: "hub-detail",
  path: "/hub/detail/:labUid/:projectUid/:protocolUid",
  beforeEnter: to => resolveHubDetailRedirect(to),
  component: () => import("@/views/hub/protocol-detail.vue"),
  children: [
    {
      path: "protocol",
      name: "hub-detail-protocol",
      meta: { title: "Hub Protocol Detail", allowGuest: true },
      component: () => import("@/views/hub/hub-detail-protocol.vue"),
    },
    {
      path: "records",
      name: "hub-detail-record",
      meta: { title: "Hub Protocol Records", allowGuest: true },
      component: () => import("@/views/project-protocols/protocol-records.vue"),
    },
    {
      path: "discussions",
      name: "hub-detail-discussion",
      meta: { title: "Hub Protocol Discussions", allowGuest: true },
      component: () => import("@/views/project-protocols/protocol-discussion.vue"),
    },
  ],
}

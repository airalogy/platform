import type { CustomRoute, ProtocolInfoNameKey } from "#/page-route"

export const protocolInfoRoute: CustomRoute<ProtocolInfoNameKey> = {
  meta: { i18nKey: "page.protocol.info", title: "protocol info", hideInMenu: true, allowGuest: true },
  path: "/labs/:labUid([\\w-]+)/projects/:projectUid([\\w-_]+)/protocols/:protocolUid([\\w-_]+)",
  component: () => import("@/views/project-protocols/layout/tabs-layout.vue"),
  children: [
    {
      path: "",
      name: "protocol-info",
      meta: { title: "Protocol Info", hideInMenu: true, allowGuest: true },
      redirect: { name: "protocol-detail" },
    },
    {
      path: "discussions/:questionId",
      name: "protocol-discussion-detail",
      meta: { i18nKey: "page.protocol.tab.discussion", title: "protocol discussion detail", allowGuest: true },
      component: () => import("@/views/project-protocols/modules/discussion/protocol-discussion-detail.vue"),
    },
    {
      path: "discussions/:questionId/edit",
      name: "protocol-discussion-edit",
      meta: { i18nKey: "page.protocol.tab.discussion", title: "edit protocol discussion", allowGuest: false },
      component: () => import("@/views/project-protocols/modules/discussion/protocol-discussion-edit.vue"),
    },
    {
      path: "protocol",
      name: "protocol-detail",
      meta: { i18nKey: "page.protocol.tab.protocols", title: "protocol detail", allowGuest: true },
      component: () => import("@/views/project-protocols/protocol-info.vue"),
    },
    {
      path: "records",
      name: "protocol-records",
      meta: { i18nKey: "page.protocol.tab.logs", title: "protocol records", allowGuest: true },
      component: () => import("@/views/project-protocols/protocol-records.vue"),
    },
    {
      path: "discussions",
      name: "protocol-discussions",
      meta: { i18nKey: "page.protocol.tab.discussion", title: "protocol discussions", allowGuest: true },
      component: () => import("@/views/project-protocols/protocol-discussion.vue"),
    },
    {
      path: "settings",
      name: "protocol-settings",
      meta: { i18nKey: "page.protocol.tab.settings", title: "protocol settings", allowGuest: false },
      component: () => import("@/views/project-protocols/protocol-settings.vue"),
    },
    {
      path: "new",
      name: "protocol-info-apply-protocol",
      meta: { title: "apply protocol", allowGuest: false },
      component: () => import("@/views/project-protocols/modules/protocol/apply-protocol.vue"),
    },
  ],
}

export const protocolEditorRoute: CustomRoute = {
  path: "/labs/:labUid([\\w-]+)/projects/:projectUid([\\w-_]+)/:protocolUid([\\w-_]+)/editor/v:protocolVersion([\\w-_.]+)?",
  component: () => import("@/views/editor/index.vue"),
  meta: { title: "Airalogy Protocol Editor", icon: "edit", hideInMenu: true },
  name: "protocol-editor",
}

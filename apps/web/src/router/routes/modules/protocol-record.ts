import type { CustomRoute, ProtocolRecordNameKey } from "#/page-route"

export const protocolRecordRoute: CustomRoute<ProtocolRecordNameKey> = {
  meta: { i18nKey: "page.protocol.tab.logs", title: "protocol records", hideInMenu: true, notContainer: true },
  path: "/labs/:labUid([\\w-]+)/projects/:projectUid([\\w-_]+)/protocols/:protocolUid([\\w-_]+)",
  component: () => import("@/views/project-protocols/layout/wrapper-layout.vue"),
  children: [
    {
      path: "add",
      name: "add-protocol-record",
      meta: { i18nKey: "page.protocol.tab.logs", title: "add protocol records" },
      component: () => import("@/views/project-protocols/protocol-add-record.vue"),
    },
    {
      path: "add/chain",
      name: "add-protocol-record-from-workflow",
      meta: { i18nKey: "page.protocol.tab.logs", title: "protocol workflow" },
      component: () => import("@/views/project-protocols/protocol-add-record.vue"),
    },
    {
      path: "v:protocolVersion([\\d.]+)/record/:recordId/v:recordVersion([\\d.]+)",
      name: "protocol-record-report",
      meta: { title: "protocol record report", allowGuest: true },
      component: () => import("@/views/project-protocols/record-report.vue"),
    },
  ],
}

import type { CustomRoute, LabsNameKey } from "#/page-route"

export const labsRoute: CustomRoute<LabsNameKey> = {
  meta: { title: "Labs", i18nKey: "common.labs", breadcrumbI18nKey: "breadcrumb.allLabs" },
  name: "labs",
  path: "/labs",
  redirect: "/labs/my",
  component: () => import("@/views/labs/layout.vue"),
  children: [
    {
      meta: {
        title: "My labs",
        i18nKey: "page.labs.my",
        breadcrumbI18nKey: "breadcrumb.myLabs",
      },
      path: "my",
      name: "labs-my",
      component: () => import("@/views/labs/my.vue"),
    },
    // {
    //   meta: {
    //     title: "Public Labs",
    //     breadcrumbI18nKey: "breadcrumb.publicLabs",
    //     i18nKey: "page.labs.public",
    //   },
    //   path: "public",
    //   name: "labs-public",
    //   component: () => import("@/views/labs/public.vue"),
    // },
  ],
}

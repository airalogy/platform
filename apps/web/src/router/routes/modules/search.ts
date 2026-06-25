import type { CustomRoute, SearchNameKey } from "#/page-route"

export const searchRoute: CustomRoute<SearchNameKey> = {
  name: "search",
  path: "/search",
  component: () => import("@/views/search/layout.vue"),
  meta: {
    title: "Search",
    i18nKey: "page.search.title",
    requiresAuth: true,
    icon: "ion:search-outline",
  },
  children: [
    {
      path: "protocol",
      name: "search-protocol",
      component: () => import("@/views/search/protocol.vue"),
      meta: {
        title: "Protocol Search",
        i18nKey: "page.search.protocol",
      },
    },
    {
      path: "record",
      name: "search-record",
      component: () => import("@/views/search/record.vue"),
      meta: {
        title: "Record Search",
        i18nKey: "page.search.record",
      },
    },
    {
      path: "discussion",
      name: "search-discussion",
      component: () => import("@/views/search/discussion.vue"),
      meta: {
        title: "Discussion Search",
        i18nKey: "page.search.discussion",
      },
    },
  ],
}

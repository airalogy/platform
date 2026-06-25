import type { CustomRoute, UserProfileNameKey } from "#/page-route"

export const userProfileRoute: CustomRoute<UserProfileNameKey> = {
  meta: {
    title: "Profile",
    i18nKey: "common.profile",
    breadcrumbI18nKey: "breadcrumb.allProfile",
    hideInMenu: true,
  },
  path: "/users/:username([\\w-_]+)",
  component: () => import("@/views/profile/layout.vue"),
  children: [
    {
      meta: { title: "User Profile" },
      path: "",
      name: "user-profile",
      component: () => import("@/views/profile/modules/summary.vue"),
    },
    {
      meta: { title: "Account Settings" },
      path: "settings",
      name: "profile-settings",
      component: () => import("@/views/profile/modules/settings.vue"),
    },
    {
      meta: { title: "User Questions" },
      path: "questions",
      name: "profile-questions",
      component: () => import("@/views/profile/modules/questions.vue"),
    },
    {
      meta: { title: "User Answers" },
      path: "answers",
      name: "profile-answers",
      component: () => import("@/views/profile/modules/answers.vue"),
    },
    {
      meta: { title: "User Protocols" },
      path: "protocols",
      name: "profile-protocols",
      component: () => import("@/views/profile/modules/protocols.vue"),
    },
    {
      meta: { title: "User Records" },
      path: "records",
      name: "profile-records",
      component: () => import("@/views/record-diary/index.vue"),
    },
    {
      meta: { title: "User Starred" },
      path: "starred",
      name: "profile-starred",
      component: () => import("@/views/profile/modules/starred.vue"),
    },
  ],
}

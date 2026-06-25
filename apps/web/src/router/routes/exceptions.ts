import type { CustomRoute, ExceptionNameKey } from "#/page-route"
import BlankLayout from "@/layouts/blank-layout/index.vue"

export const exceptionRoutes: CustomRoute<ExceptionNameKey>[] = [
  {
    meta: { title: "LAB NOT FOUND", constant: true },
    path: "/404/lab",
    name: "lab-not-found",
    component: () => import("@/views/exceptions/404/lab.vue"),
  },
  {
    meta: { title: "PROJECT NOT FOUND", constant: true },
    path: "/404/project",
    name: "project-not-found",
    component: () => import("@/views/exceptions/404/project.vue"),
  },
  {
    meta: { title: "PROTOCOL NOT FOUND", constant: true },
    path: "/404/protocol",
    name: "protocol-not-found",
    component: () => import("@/views/exceptions/404/protocol.vue"),
  },
  {
    meta: { title: "404 NOT FOUND", constant: true },
    path: "/404",
    name: "404",
    component: BlankLayout,
    children: [
      {
        component: () => import("@/views/exceptions/404/index.vue"),
        meta: { title: "404", i18nKey: "route.404", constant: true },
        name: "not-found",
        path: "",
      },
    ],
  },
  {
    meta: { title: "403 FORBIDDEN", constant: true },
    path: "/403",
    name: "403",
    component: BlankLayout,
    children: [
      {
        component: () => import("@/views/exceptions/403/index.vue"),
        meta: { title: "403", i18nKey: "route.403", constant: true },
        name: "no-permission",
        path: "",
      },
    ],
  },
  {
    meta: { title: "500 SERVER ERROR", constant: true },
    path: "/500",
    name: "500",
    component: BlankLayout,
    children: [
      {
        component: () => import("@/views/exceptions/500/index.vue"),
        meta: { title: "500", i18nKey: "route.500", constant: true },
        name: "server-error",
        path: "",
      },
    ],
  },
  {
    meta: { title: "not-found", constant: true },
    path: "/:pathMatch(.*)*",
    component: () => import("@/layouts/blank-layout/index.vue"),
    children: [
      {
        component: () => import("@/views/exceptions/404/index.vue"),
        name: "path-not-found",
        path: "",
        props: true,
      },
    ],
  },
  // {
  //   name: "not-found",
  //   path: "/:pathMatch(.*)*",
  //   component: "layout.blank$view.404",
  //   meta: {
  //     title: "not-found",
  //     constant: true,
  //   },
  // },
  // {
  //   name: "exception",
  //   path: "/exception",
  //   component: "layout.base",
  //   meta: {
  //     title: "exception",
  //     i18nKey: "route.exception",
  //     icon: "ant-design:exception-outlined",
  //     order: 7,
  //   },
  //   children: [
  //     {
  //       name: "exception_403",
  //       path: "/exception/403",
  //       component: "view.403",
  //       meta: {
  //         title: "exception_403",
  //         i18nKey: "route.exception_403",
  //         icon: "ic:baseline-block",
  //       },
  //     },
  //     {
  //       name: "exception_404",
  //       path: "/exception/404",
  //       component: "view.404",
  //       meta: {
  //         title: "exception_404",
  //         i18nKey: "route.exception_404",
  //         icon: "ic:baseline-web-asset-off",
  //       },
  //     },
  //     {
  //       name: "exception_500",
  //       path: "/exception/500",
  //       component: "view.500",
  //       meta: {
  //         title: "exception_500",
  //         i18nKey: "route.exception_500",
  //         icon: "ic:baseline-wifi-off",
  //       },
  //     },
  //   ],
  // },
]

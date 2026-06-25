import type { AuthRouteNameKey, CustomRoute } from "#/page-route"

export const authRoute: CustomRoute<AuthRouteNameKey> = {
  meta: { title: "User", constant: true },
  name: "auth",
  path: "/auth",
  component: () => import("@/views/auth/auth-layout.vue"),
  children: [
    {
      meta: { title: "Log in" },
      path: "/login",
      name: "login",
      component: () => import("@/views/auth/login.vue"),
    },
    {
      meta: { title: "Sign up" },
      path: "/sign-up",
      name: "sign-up",
      component: () => import("@/views/auth/sign-up.vue"),
    },
    {
      meta: { title: "Forget Password" },
      path: "/forget-password",
      name: "forget-password",
      component: () => import("@/views/auth/forget-password.vue"),
    },
  ],
}

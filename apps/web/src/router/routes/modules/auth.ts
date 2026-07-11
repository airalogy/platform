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
    {
      meta: { title: "Set up Airalogy Lab" },
      path: "/setup",
      name: "instance-setup",
      component: () => import("@/views/auth/instance-setup.vue"),
    },
    {
      meta: { title: "Join Lab" },
      path: "/join",
      name: "join-lab",
      component: () => import("@/views/auth/join-lab.vue"),
    },
    {
      meta: { title: "Reset Password" },
      path: "/reset-password",
      name: "password-reset",
      component: () => import("@/views/auth/password-reset.vue"),
    },
  ],
}

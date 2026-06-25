import type { App } from "vue"
import {
  createRouter,
  createWebHistory,
} from "vue-router"
import { createRouterGuard } from "./guard"
import { createRoutes } from "./routes"

const { constantRoutes, authRoutes } = createRoutes()

export const router = createRouter({
  history: createWebHistory("/"),
  routes: [...constantRoutes, ...authRoutes],
})

/** Setup Vue Router */
export async function setupRouter(app: App) {
  app.use(router)
  createRouterGuard(router)

  await router.isReady()
}

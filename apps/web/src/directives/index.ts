import type { App } from "vue"
import { vAuth } from "./auth"
import { vHide } from "./hide"

export function setupDirectives(app: App) {
  app.directive("hide", vHide)
  app.directive("auth", vAuth)
}

export default setupDirectives

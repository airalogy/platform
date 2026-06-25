import type { Router } from "vue-router"
import { useGlobalBeforeUnload } from "@airalogy/composables"

/**
 * Creates a guard that prevents navigation when there are unsaved changes
 *
 * @param router - Router instance
 */
export async function createUnsavedChangesGuard(router: Router) {
  const globalRegistry = useGlobalBeforeUnload()

  router.beforeEach(async (to, from, next) => {
    // 开发环境中禁用关闭提示
    if (import.meta.env.DEV) {
      next()
      return
    }

    // If there are no unsaved changes, allow navigation
    if (from.path === to.path || !globalRegistry.hasUnsavedChangesByPath(from.fullPath)) {
      next()
      return
    }

    // Ask for confirmation

    let confirmed = false
    if (window.$dialog) {
      confirmed = await new Promise((resolve) => {
        window.$dialog!.warning({
          title: "Unsaved Changes",
          content: "You have unsaved changes. Are you sure you want to leave?",
          positiveText: "Yes",
          negativeText: "No",
          transformOrigin: "center",
          onPositiveClick: () => resolve(true),
          onNegativeClick: () => resolve(false),
        })
      })
    }
    else {
      // eslint-disable-next-line no-alert
      confirmed = window.confirm("You have unsaved changes. Are you sure you want to leave?")
    }

    if (confirmed) {
      // Clear the registry when user confirms navigation
      globalRegistry.unregister(from.fullPath)
      next()
    }
    else {
      // Prevent navigation
      next(false)
    }
  })
}

import { router } from "@/router"
import { clearAuthStorage } from "@/store/modules/auth/shared"

let showUnauthorizedMessage = true

export function handleUnauthorized() {
  if (showUnauthorizedMessage) {
    window.$message?.error("Authentication required")
    showUnauthorizedMessage = false
  }

  clearAuthStorage()
  void router.push({ name: "login" }).then(() => {
    setTimeout(() => {
      showUnauthorizedMessage = true
    }, 100)
  })
}

export function registerUnauthorizedHandler() {
  (window as any).$handleUnauthorized = handleUnauthorized
}

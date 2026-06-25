import type { Directive, DirectiveBinding } from "vue"
import { useAuthStore } from "@/store/modules/auth"

export interface AuthDirectiveOptions {
  requireLogin?: boolean
  checkAuth?: () => boolean
}

export const vAuth: Directive = {
  mounted(el: HTMLElement, binding: DirectiveBinding<AuthDirectiveOptions>) {
    const authStore = useAuthStore()

    const originalClick = el.onclick

    el.onclick = async (e: MouseEvent) => {
      const { requireLogin = true, checkAuth } = binding.value || {}

      if (window.$message) {
        if (requireLogin && !authStore.isLogin) {
          window.$message.info("Authentication required")
          return
        }

        if (checkAuth && !checkAuth()) {
          window.$message.error("Permission denied.")
          return
        }
      }

      if (originalClick) {
        originalClick.call(el, e)
      }
    }
  },
}

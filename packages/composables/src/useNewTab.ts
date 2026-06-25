import type { RouteLocationRaw } from "vue-router"
import { useDialog } from "naive-ui"

export function useOpenNewTab<T extends string>() {
  const router = useRouter()
  const dialog = useDialog()

  const openNewTab = (options: RouteLocationRaw) => {
    const url = router.resolve(options).href // 生成完整 URL
    const handler = window.open(url, "_blank") // 在新标签页中打开
    if (!handler) {
      dialog.error({
        title: "Failed to open new tab",
        content: "Please manually open the link in a new tab.",
        positiveText: "OK",
      })
    }
  }

  return { router, openNewTab }
}

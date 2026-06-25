import type { UploadFileInfo as BaseUploadFileInfo } from "naive-ui"

import "naive-ui"

declare module "naive-ui" {
  interface TabPaneSlots {
    tab?: () => VNode[]
  }

  interface UploadFileInfo extends BaseUploadFileInfo {
    airalogyId?: string
  }
}

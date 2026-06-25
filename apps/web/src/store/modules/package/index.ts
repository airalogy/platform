import type { ProtocolModels } from "@airalogy/shared/types"
import { SetupStoreId } from "@/enum"
import { defineStore } from "pinia"

export const usePackageStore = defineStore(SetupStoreId.PACKAGE, () => {
  /** Protocol Package */
  const protocolCache = ref<ProtocolModels.ProjectProtocolInfo | null>()

  return {
    protocolCache,
  }
})

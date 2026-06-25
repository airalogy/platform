import { SetupStoreId } from "@/enum"
import { defineStore } from "pinia"
import { ref } from "vue"

export const useModalStore = defineStore(SetupStoreId.TAB, () => {
  /** Tabs */
  const modals = ref<App.Global.Modal[]>([])

  /** Get active tab */
  const activeModal = ref<App.Global.Modal>()

  return {
    modals,
    activeModal,
  }
})

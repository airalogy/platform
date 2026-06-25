import { defineStore } from "pinia"
import { getLocalPromptList, setLocalPromptList } from "./helper"

export const usePromptStore = defineStore("prompt-store", {
  state: () => getLocalPromptList(),

  actions: {
    updatePromptList(promptList: string[]) {
      this.$patch({ promptList })
      setLocalPromptList({ promptList })
    },
    getPromptList() {
      return this.$state
    },
  },
})

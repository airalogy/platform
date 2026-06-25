import { defineStore } from "pinia"

export const useArticleStore = defineStore("article-store", {
  state: () => ({
    articleListRecord: <Record<string, string>>{},
  }),

  actions: {},
})

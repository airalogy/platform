import { defineStore } from "pinia"

export const useStyleStore = defineStore("style", {
  state: () => {
    return {
      uiStyle: localStorage.getItem("ui-style") || "normal",
    }
  },
  getters: {
    isElder: state => state.uiStyle === "elder",
  },
  actions: {
    toggleStyle() {
      this.uiStyle = this.uiStyle === "normal" ? "elder" : "normal"
      localStorage.setItem("ui-style", this.uiStyle)
    },
  },
})

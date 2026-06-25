import { defineStore } from "pinia"
import { ref } from "vue"

export interface DragIconRef {
  element: HTMLElement | null
}

export const useDragIconStore = defineStore("dragIcon", () => {
  const dragIconRef = ref<DragIconRef>({ element: null })

  function setDragIconRef(element: HTMLElement | null) {
    dragIconRef.value.element = element
  }

  return {
    dragIconRef,
    setDragIconRef,
  }
})

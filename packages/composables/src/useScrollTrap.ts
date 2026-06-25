import { type MaybeRefOrGetter, onMounted, onUnmounted } from "vue"

/**
 * Scroll trap composable to prevent scrolling outside of an element
 * @param elementRef - Reference to the element to trap scrolling within
 */
export function useScrollTrap(elementRef: MaybeRefOrGetter<HTMLElement | null>) {
  function handleWheel(event: WheelEvent) {
    const element = unrefElement(elementRef)
    if (!element)
      return

    const { deltaY } = event
    const { scrollTop, scrollHeight, clientHeight } = element

    // Scrolling up and already at the top
    if (deltaY < 0 && scrollTop <= 0) {
      event.preventDefault()
      return
    }

    // Scrolling down and already at the bottom
    if (deltaY > 0 && scrollTop + clientHeight >= scrollHeight) {
      event.preventDefault()
    }
  }

  onMounted(() => {
    const element = unrefElement(elementRef)
    if (!element)
      return

    element.addEventListener("wheel", handleWheel, { passive: false })
  })

  onUnmounted(() => {
    const element = unrefElement(elementRef)
    if (!element)
      return

    element.removeEventListener("wheel", handleWheel)
  })
}

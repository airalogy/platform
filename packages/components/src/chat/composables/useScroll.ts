import type { UseScrollReturn } from "@vueuse/core"
import type { Ref } from "vue"
import { useScroll as useVueUseScroll } from "@vueuse/core"
import { computed, nextTick, ref } from "vue"

type ScrollElement = HTMLElement | null

interface ScrollReturn extends UseScrollReturn {
  scrollRef: Ref<ScrollElement>
  scrollToBottom: (options?: { smart?: boolean, instant?: boolean }) => Promise<void>
  scrollToTop: () => Promise<void>
  isScrollable: Ref<boolean>
}

export function useScroll(elRef?: Ref<ScrollElement>): ScrollReturn {
  const scrollRef = ref<ScrollElement>(elRef?.value || null)
  if (elRef) {
    watchOnce(elRef, (el) => {
      scrollRef.value = el
    })
  }

  // Use VueUse's useScroll with throttling and smooth behavior
  const { y, isScrolling, arrivedState, x, directions, measure } = useVueUseScroll(computed(() => unrefElement(scrollRef)), {
    throttle: 100, // Add throttling for better performance
    behavior: "smooth", // Enable smooth scrolling
    offset: { bottom: 200 }, // Match the existing threshold
  })

  // Computed property to determine if element is scrollable
  const isScrollable = computed(() => {
    const el = unrefElement(scrollRef)
    if (!el)
      return false

    // Check if content is scrollable vertically or horizontally
    const hasVerticalScroll = el.scrollHeight > el.clientHeight
    const hasHorizontalScroll = el.scrollWidth > el.clientWidth

    return hasVerticalScroll || hasHorizontalScroll
  })

  /**
   * Scroll to bottom with configurable behavior
   * @param options.smart - If true, only scroll when user is near bottom (default: false)
   * @param options.instant - If true, scroll without animation (default: true)
   */
  const scrollToBottom = async (options: { smart?: boolean, instant?: boolean } = {}) => {
    const { smart = false, instant = true } = options

    await nextTick()
    const el = unrefElement(scrollRef)
    if (!el)
      return

    // Smart scroll: check if user is near bottom
    if (smart) {
      const threshold = 200
      const distanceToBottom = el.scrollHeight - el.clientHeight - el.scrollTop

      if (distanceToBottom > threshold) {
        // User is viewing history, don't scroll
        return
      }
    }

    // Perform scroll
    if (instant) {
      // Instant scroll without animation
      el.scrollTo({
        top: el.scrollHeight - el.clientHeight,
        behavior: "instant",
      })
    }
    else {
      // Smooth scroll with animation
      y.value = el.scrollHeight - el.clientHeight
    }
  }

  const scrollToTop = async () => {
    await nextTick()
    y.value = 0
  }

  return {
    scrollRef,
    scrollToBottom,
    scrollToTop,
    isScrolling,
    arrivedState,
    x,
    y,
    directions,
    measure,
    isScrollable,
  }
}

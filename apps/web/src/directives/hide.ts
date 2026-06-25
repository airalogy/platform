import type { DirectiveBinding, ObjectDirective } from "vue"

/**
 * Vue directive to hide elements while preserving their space in the DOM
 * Unlike v-show (which uses display:none), v-hide uses positioning and opacity
 * to make elements invisible while maintaining their layout impact
 *
 * Usage:
 * v-hide="condition"
 */
export const vHide: ObjectDirective = {
  mounted(el: HTMLElement, binding: DirectiveBinding) {
    updateVisibility(el, binding.value)
  },
  updated(el: HTMLElement, binding: DirectiveBinding) {
    updateVisibility(el, binding.value)
  },
  unmounted(el: HTMLElement) {
    resetStyles(el)
  },
}

/**
 * Updates the visibility of an element based on the binding value
 */
function updateVisibility(el: HTMLElement, shouldHide: boolean) {
  if (shouldHide) {
    if (!el.style.width) {
      el.style.width = `${el.clientWidth}px`
      el.dataset.restoreWidth = "true"
    }

    if (!el.style.height) {
      el.style.height = `${el.clientHeight}px`
      el.dataset.restoreHeight = "true"
    }

    // Apply styles to hide while preserving space
    el.style.position = "fixed"
    el.style.visibility = "hidden"
    el.style.pointerEvents = "none"
    el.style.zIndex = "-1"
  }
  else {
    resetStyles(el)
  }
}

/**
 * Resets all styles applied by the directive
 */
function resetStyles(el: HTMLElement) {
  el.style.position = ""
  el.style.visibility = ""
  el.style.pointerEvents = ""
  el.style.zIndex = ""
  if (el.dataset.restoreWidth) {
    el.style.width = ""
    delete el.dataset.restoreWidth
  }
  if (el.dataset.restoreHeight) {
    el.style.height = ""
    delete el.dataset.restoreHeight
  }
}

export default vHide

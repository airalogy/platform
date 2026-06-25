import { createGlobalState, useEventListener } from "@vueuse/core"
import { ref } from "vue"

// Global registry to track components with unsaved changes
export const useGlobalBeforeUnload = createGlobalState(() => {
  const componentsWithUnsavedChanges = ref(new Set<string>())

  const register = (id: string) => {
    componentsWithUnsavedChanges.value.add(id)
  }

  const unregister = (id: string) => {
    componentsWithUnsavedChanges.value.delete(id)
  }

  const hasUnsavedChanges = computed(() => componentsWithUnsavedChanges.value.size > 0)
  const hasUnsavedChangesByPath = (path: string) => componentsWithUnsavedChanges.value.has(path)

  return {
    componentsWithUnsavedChanges,
    register,
    unregister,
    hasUnsavedChanges,
    hasUnsavedChangesByPath,
  }
})

/**
 * Composable to handle browser tab close confirmation
 *
 * @param checkUnsavedFn - Function that returns true if there are unsaved changes
 * @param options - Additional options for the composable
 * @returns Methods to control the confirmation behavior
 */
export function useBeforeUnload(
  checkUnsavedFn = () => true,
  options: {
    /** Custom message to show in the confirmation dialog (note: most modern browsers ignore custom messages) */
    message?: string
    /** Whether to enable the confirmation on component mount */
    enableOnMount?: boolean
    /** Unique ID for this component (required for router integration) */
    id?: string
  } = {},
) {
  const route = useRoute()

  const {
    message = "You have unsaved changes. Are you sure you want to leave?",
    enableOnMount = true,
    id = route.fullPath,
  } = options

  const globalRegistry = useGlobalBeforeUnload()
  const isEnabled = ref(enableOnMount)
  const hasAttemptedClose = ref(false)

  const toggle = (value?: boolean) => {
    const newValue = value !== undefined ? value : !isEnabled.value
    isEnabled.value = newValue

    // Update global registry
    if (newValue && checkUnsavedFn()) {
      globalRegistry.register(id)
    }
    else {
      globalRegistry.unregister(id)
    }
  }

  // Initially set the state if enabled
  if (enableOnMount && checkUnsavedFn()) {
    globalRegistry.register(id)
  }

  /**
   * Event handler for beforeunload
   *
   * Modern browsers have standardized the behavior:
   * - Custom messages are ignored in most browsers
   * - The browser shows its own standard message
   * - Setting returnValue or returning a string triggers the confirmation
   *
   * [MDN Reference](https://developer.mozilla.org/docs/Web/API/Window/beforeunload_event)
   */
  const handleBeforeUnload = (event?: BeforeUnloadEvent) => {
    // 开发环境中禁用关闭提示
    if (import.meta.env.DEV) {
      return
    }

    if (!isEnabled.value) {
      return
    }

    const hasUnsavedChanges = checkUnsavedFn()
    hasAttemptedClose.value = true

    // Update the registry
    if (hasUnsavedChanges) {
      globalRegistry.register(id)
    }
    else {
      globalRegistry.unregister(id)
    }

    if (!hasUnsavedChanges) {
      return
    }

    // Modern browsers standardized the behavior:
    // - Custom messages are ignored in most browsers
    // - Returning a string or setting returnValue still triggers the confirmation
    if (event) {
      event.preventDefault()
      event.returnValue = message
    }

    return message // This return is needed for older browsers
  }

  // Use VueUse's useEventListener for automatic cleanup
  const cleanup = useEventListener(
    window,
    "beforeunload",
    handleBeforeUnload,
    { capture: true },
  )

  return {
    isEnabled,
    toggle,
    hasAttemptedClose,
    cleanup, // Expose cleanup function from useEventListener
  }
}

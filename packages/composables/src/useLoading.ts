import { computed, ref } from "vue"
import { useBoolean } from "./useBoolean"

/**
 * Loading state management composable
 * @param initValue - Initial loading state
 * @param keys - Optional array of keys for specific loading states
 * @returns Object with loading state and control methods
 */
export function useLoading(initValue = false, keys?: string[]) {
  const { bool: loading, setTrue: startLoading, setFalse: endLoading } = useBoolean(initValue)

  const loadingState = ref<Record<string, boolean>>(
    keys ? Object.fromEntries(keys.map(key => [key, initValue])) : {},
  )

  const setLoading = (key: string, value: boolean) => {
    loadingState.value[key] = value
  }

  const endTargetLoading = (key: string) => {
    loadingState.value[key] = false
  }

  const startTargetLoading = (key: string) => {
    loadingState.value[key] = true
  }

  const loadingKeys = computed(() => {
    return Object.values(loadingState.value).filter(Boolean)
  })

  return {
    loading,
    loadingState,
    loadingKeys,
    startLoading,
    endLoading,
    setLoading,
    endTargetLoading,
    startTargetLoading,
  }
}

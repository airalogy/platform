import { ref } from "vue"

/**
 * Boolean state management composable
 * @param initValue - Initial boolean value
 * @returns Object with boolean state and control methods
 */
export function useBoolean(initValue = false) {
  const bool = ref(initValue)

  function setBool(value: boolean) {
    bool.value = value
  }

  function setTrue() {
    setBool(true)
  }

  function setFalse() {
    setBool(false)
  }

  function toggle() {
    setBool(!bool.value)
  }

  return {
    bool,
    setBool,
    setTrue,
    setFalse,
    toggle,
  }
}

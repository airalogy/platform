import { type MaybeRef, type Ref, toValue, watchEffect } from "vue"

/**
 * Synchronizes a value to an input mirror element
 * Used to properly display input values in custom input components
 *
 * @param value - The value to sync to the mirror
 * @param componentInst - The component instance reference
 * @param type - The input type (e.g., 'text', 'textarea')
 * @param props - The component props object
 * @returns Object with utility values that the component might need
 */
export function syncValueToMirror(
  value: string,
  componentInst: any,
  type?: string,
  props?: Record<string, any>,
) {
  const syncValueKey = props && "formattedValue" in props ? "formattedValue" : "value"

  // Return early if no component instance
  if (!componentInst) {
    return {
      syncValueKey,
      shouldSyncValueToMirror: false,
    }
  }

  let shouldSyncValueToMirror = false

  // Get references from the component instance
  const { inputMirrorElRef, textareaMirrorElRef, inputInstRef } = componentInst
  let el = type === "textarea" ? textareaMirrorElRef : inputMirrorElRef

  // Try to find the mirror element
  if (!el && inputInstRef) {
    const { inputMirrorElRef, textareaMirrorElRef, wrapperElRef, inputElRef } = inputInstRef

    if (textareaMirrorElRef) {
      el = textareaMirrorElRef
    }
    else if (inputMirrorElRef) {
      el = inputMirrorElRef
    }
    else if (wrapperElRef) {
      const target = (wrapperElRef as HTMLDivElement).querySelector(".n-input__input")
      if (target) {
        // Create and setup the mirror element
        const newEl = document.createElement("div")
        newEl.classList.add("n-input__input-mirror")

        // Position the input element
        if (inputElRef) {
          inputElRef.style.position = "absolute"
          inputElRef.style.top = "0"
          inputElRef.style.left = "0"
          inputElRef.style.height = "100%"
        }

        // Append mirror element
        target.appendChild(newEl)
        inputInstRef.inputMirrorElRef = newEl

        el = newEl

        shouldSyncValueToMirror = true
      }
    }
  }

  if (el) {
    // Set content based on input type
    if (type === "textarea") {
      el.textContent = `${value ?? ""}\r\n`
    }
    else {
      if (value) {
        el.textContent = value
      }
      else {
        el.innerHTML = "&nbsp;"
      }
    }
  }

  return {
    syncValueKey,
    shouldSyncValueToMirror,
  }
}

/**
 * Setup watchers for input mirror synchronization
 * To be used in a component with Vue's composition API
 *
 * @param componentInstRef - Ref to the component instance
 * @param props - Component props containing componentProps
 * @param syncValueKey - Ref to the sync value key (e.g., 'value', 'formattedValue')
 * @param shouldSyncValueToMirror - Ref indicating if mirroring should be active
 */
export function useSyncInputMirror(
  componentInstRef: any,
  props: MaybeRef<any>,
  syncValueKey: Ref<string>,
  shouldSyncValueToMirror: any,
) {
  /**
   * Helper function to synchronize text to mirror element
   * @param text - Text to synchronize
   * @param propsValue - Resolved props values
   */
  const syncTextToMirror = (text: string, propsValue: Record<string, any>) => {
    const componentInst = toValue(componentInstRef)
    const { type } = propsValue

    const result = syncValueToMirror(
      text,
      componentInst,
      type,
      propsValue,
    )

    // Update sync key if needed
    if (result.syncValueKey !== syncValueKey.value) {
      syncValueKey.value = result.syncValueKey
    }

    // Update sync flag if needed
    if (result.shouldSyncValueToMirror !== shouldSyncValueToMirror.value) {
      shouldSyncValueToMirror.value = result.shouldSyncValueToMirror
    }

    return result
  }

  // Use watchEffect to reactively handle all changes
  watchEffect(() => {
    const componentInst = toValue(componentInstRef)
    if (!componentInst) {
      return
    }

    const propsValue = toValue(props)
    const key = syncValueKey.value
    const currentValue = propsValue[key]

    if (currentValue) {
      // If we have a value, sync it to the mirror
      syncTextToMirror(currentValue, propsValue)
    }
    else {
      // Otherwise, use placeholder if available
      shouldSyncValueToMirror.value = false
      const { placeholder } = propsValue

      if (typeof placeholder === "string") {
        syncTextToMirror(placeholder, propsValue)
      }
    }
  })
}

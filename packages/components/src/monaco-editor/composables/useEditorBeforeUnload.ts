import type { Ref } from "vue"
import { useBeforeUnload } from "@airalogy/composables"
import { computed } from "vue"
import { type DiffModelInfo, isNormalModelInfo, type ModelInfo } from "../store/editorStore"

/**
 * Specialized composable that combines useBeforeUnload with editor state checking
 * to handle browser tab closing confirmation when there are unsaved changes in editor
 *
 * @param modelsInfoRef - Reference to the model info array from the editor store
 * @param isReadOnly - Whether the editor is in read-only mode
 * @returns Methods to control the unload confirmation behavior
 */
export function useEditorBeforeUnload(
  modelsInfoRef: Ref<(ModelInfo | DiffModelInfo)[]>,
  isReadOnly: Ref<boolean>,
) {
  // Check if any model has unsaved changes (isDirty)
  const checkUnsavedChanges = () => {
    // If editor is read-only, no need to check for unsaved changes
    if (isReadOnly.value) {
      return false
    }

    // If any model is dirty, we have unsaved changes
    return modelsInfoRef.value.some(model => isNormalModelInfo(model) && model.isDirty)
  }

  // Create computed prop to get the current unsaved state for external use
  const hasUnsavedChanges = computed(checkUnsavedChanges)

  const {
    isEnabled,
    hasAttemptedClose,
  } = useBeforeUnload(checkUnsavedChanges, { enableOnMount: true })

  return {
    isEnabled,
    hasUnsavedChanges,
    hasAttemptedClose,
  }
}

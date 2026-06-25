import { useClosableMessage, useLoading } from "@airalogy/composables"

export function useDeleteConfirmation(
  onDelete: () => Promise<{ data?: any, error?: any }>,
  entityName: string,
  onSuccess?: () => void,
  onError?: (error: any) => void,
) {
  const showDeleteModal = ref(false)
  const deleteConfirmationText = ref("")
  const { loading: deleting, startLoading: startDeleting, endLoading: endDeleting } = useLoading()
  const message = useClosableMessage()

  // Computed property to validate delete confirmation
  const isDeleteConfirmationValid = computed(() => {
    return deleteConfirmationText.value === "DELETE"
  })

  function handleDelete() {
    showDeleteModal.value = true
  }

  function cancelDelete() {
    showDeleteModal.value = false
    deleteConfirmationText.value = ""
  }

  async function confirmDelete() {
    if (!isDeleteConfirmationValid.value) {
      return
    }

    startDeleting()

    try {
      const { data, error } = await onDelete()

      if (error) {
        if (onError)
          onError(error)
        else message.error(`Failed to delete ${entityName.toLowerCase()}. Please try again.`)
      }
      else {
        message.success(`${entityName} deleted successfully.`)
        showDeleteModal.value = false
        deleteConfirmationText.value = ""
        if (onSuccess)
          onSuccess()
      }
    }
    catch (error) {
      if (onError)
        onError(error)
      else message.error(`Failed to delete ${entityName.toLowerCase()}. Please try again.`)
    }
    finally {
      endDeleting()
    }
  }

  return {
    showDeleteModal,
    deleteConfirmationText,
    deleting,
    isDeleteConfirmationValid,
    handleDelete,
    cancelDelete,
    confirmDelete,
  }
}

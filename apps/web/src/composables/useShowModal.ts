import { useBoolean } from "@airalogy/composables"

/**
 * Show modal status
 *
 * @param initValue Init value
 */
export function useShowModal(initValue = false) {
  const { bool: isShown, setTrue: showModal, setFalse: hideModal, setBool: setModalStatus } = useBoolean(initValue)

  return {
    isShown,
    showModal,
    hideModal,
    setModalStatus,
  }
}

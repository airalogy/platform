import { computed, onUnmounted, ref, type Ref } from "vue"

type ResizeDirection = "left" | "right"
export interface ElementDimensions {
  width: number
  height: number
}

interface HookParams {
  initialWidth?: number
  initialHeight?: number
  contentWidth?: number
  contentHeight?: number
  gridInterval: number
  minWidth: number
  minHeight: number
  maxWidth: Ref<number>
  containerMaxWidth: Ref<number>
  onDimensionsChange?: (dimensions: ElementDimensions) => void
}

export function useDragResize({
  initialWidth,
  initialHeight,
  contentWidth,
  contentHeight,
  gridInterval,
  minWidth,
  minHeight,
  maxWidth,
  containerMaxWidth,
  onDimensionsChange,
}: HookParams) {
  const dimensions = ref<ElementDimensions>({
    width: Math.max(initialWidth ?? minWidth, minWidth),
    height: Math.max(initialHeight ?? minHeight, minHeight),
  })
  const boundaryWidth = ref(Infinity)
  const resizeOrigin = ref(0)
  const initialDimensions = ref(dimensions.value)
  const resizeDirection = ref<ResizeDirection | undefined>()

  const maxAllowedWidth = computed(() => Math.min(maxWidth.value, containerMaxWidth.value))

  const widthConstraint = (proposedWidth: number, maxAllowedWidth: number) => {
    const effectiveMinWidth = Math.max(
      minWidth,
      Math.min(contentWidth ?? minWidth, (gridInterval / 100) * maxAllowedWidth),
    )
    return Math.min(maxAllowedWidth, Math.max(proposedWidth, effectiveMinWidth))
  }

  const handlePointerMove = (event: PointerEvent) => {
    event.preventDefault()
    const movementDelta
      = (resizeDirection.value === "left"
        ? resizeOrigin.value - event.pageX
        : event.pageX - resizeOrigin.value) * 2
    const gridProtocolWidth = (gridInterval / 100) * boundaryWidth.value
    const proposedWidth = initialDimensions.value.width + movementDelta
    const alignedWidth = Math.round(proposedWidth / gridProtocolWidth) * gridProtocolWidth
    const finalWidth = widthConstraint(alignedWidth, boundaryWidth.value)
    const aspectRatio = contentHeight && contentWidth ? contentHeight / contentWidth : 1

    dimensions.value = {
      width: Math.max(finalWidth, minWidth),
      height: Math.max(
        contentWidth ? finalWidth * aspectRatio : (contentHeight ?? minHeight),
        minHeight,
      ),
    }
  }

  const handlePointerUp = (event: PointerEvent) => {
    event.preventDefault()
    event.stopPropagation()

    resizeOrigin.value = 0
    resizeDirection.value = undefined
    onDimensionsChange?.(dimensions.value)
  }

  const handleKeydown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault()
      event.stopPropagation()
      dimensions.value = {
        width: Math.max(initialDimensions.value.width, minWidth),
        height: Math.max(initialDimensions.value.height, minHeight),
      }
      resizeDirection.value = undefined
    }
  }

  const initiateResize = (direction: ResizeDirection) => (event: PointerEvent) => {
    event.preventDefault()
    event.stopPropagation()

    boundaryWidth.value = maxAllowedWidth.value
    initialDimensions.value = {
      width: Math.max(widthConstraint(dimensions.value.width, maxAllowedWidth.value), minWidth),
      height: Math.max(dimensions.value.height, minHeight),
    }
    resizeOrigin.value = event.pageX
    resizeDirection.value = direction
  }

  const setupListeners = () => {
    if (resizeDirection.value) {
      document.addEventListener("keydown", handleKeydown)
      document.addEventListener("pointermove", handlePointerMove)
      document.addEventListener("pointerup", handlePointerUp)
    }
  }

  const cleanupListeners = () => {
    document.removeEventListener("keydown", handleKeydown)
    document.removeEventListener("pointermove", handlePointerMove)
    document.removeEventListener("pointerup", handlePointerUp)
  }

  // Watch for resizeDirection changes
  watch(resizeDirection, (newValue) => {
    if (newValue) {
      setupListeners()
    }
    else {
      cleanupListeners()
    }
  })

  // Cleanup on component unmount
  onUnmounted(() => {
    cleanupListeners()
  })

  return {
    initiateResize,
    dimensions,
    isResizing: computed(() => !!resizeDirection.value),
    currentWidth: computed(() => Math.max(dimensions.value.width, minWidth)),
    currentHeight: computed(() => Math.max(dimensions.value.height, minHeight)),
  }
}

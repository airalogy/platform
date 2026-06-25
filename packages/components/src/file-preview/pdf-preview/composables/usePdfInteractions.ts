import { useEventListener } from "@vueuse/core"
import { computed, ref, type Ref } from "vue"

interface PanState {
  isPanning: boolean
  startX: number
  startY: number
  scrollStartX: number
  scrollStartY: number
  displayHint: boolean
}

interface ModifierKeyState {
  altKey: boolean
  spaceKey: boolean
}

export function usePdfInteractions(
  containerRef: Ref<HTMLElement | undefined>,
  scale: Ref<number>,
  isScrollMode: boolean,
  onZoomChange: (newScale: number, clientX?: number, clientY?: number) => void,
) {
  const panState = ref<PanState>({
    isPanning: false,
    startX: 0,
    startY: 0,
    scrollStartX: 0,
    scrollStartY: 0,
    displayHint: true,
  })

  const modifierKeys = ref<ModifierKeyState>({
    altKey: false,
    spaceKey: false,
  })

  // Store original scroll behavior to restore after panning
  const originalScrollBehavior = ref<string>("")

  const isDraggable = computed(() => {
    // Enable dragging if zoomed in OR if modifier keys are pressed
    return scale.value > 1.0 || modifierKeys.value.altKey || modifierKeys.value.spaceKey
  })

  // Disable smooth scrolling during panning to prevent lag
  function disableSmoothScroll() {
    if (!containerRef.value)
      return

    const computedStyle = getComputedStyle(containerRef.value)
    originalScrollBehavior.value = computedStyle.scrollBehavior || "smooth"
    containerRef.value.style.scrollBehavior = "auto"
  }

  // Restore smooth scrolling after panning
  function restoreSmoothScroll() {
    if (!containerRef.value)
      return

    containerRef.value.style.scrollBehavior = originalScrollBehavior.value
  }

  // Wheel event handler for zoom and scroll
  function handleWheel(event: WheelEvent) {
    if (!containerRef.value)
      return

    // Ctrl/Cmd + Wheel = Zoom
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault()

      const rect = containerRef.value.getBoundingClientRect()
      const clientX = event.clientX - rect.left
      const clientY = event.clientY - rect.top

      // Calculate zoom delta (more precise than button clicks)
      const zoomFactor = event.deltaY > 0 ? 0.9 : 1.1
      const newScale = Math.max(0.25, Math.min(scale.value * zoomFactor, 5.0))

      console.log(`Wheel zoom: ${scale.value.toFixed(2)} -> ${newScale.toFixed(2)} at cursor (${clientX}, ${clientY})`)
      onZoomChange(newScale, clientX, clientY)
      return
    }

    // Shift + Wheel = Horizontal scroll (only in scroll mode)
    if (event.shiftKey && isScrollMode) {
      event.preventDefault()
      containerRef.value.scrollLeft += event.deltaY
    }

    // Regular wheel = vertical scroll (default behavior)
    // No preventDefault needed, let it scroll naturally
  }

  // Keyboard event handlers for modifier keys
  function handleKeyDown(event: KeyboardEvent) {
    if (event.code === "Space") {
      modifierKeys.value.spaceKey = true
      updateCursor()
      // Prevent space from scrolling the page
      if (containerRef.value && containerRef.value.contains(document.activeElement)) {
        event.preventDefault()
      }
    }
    if (event.altKey && !modifierKeys.value.altKey) {
      modifierKeys.value.altKey = true
      updateCursor()
    }
  }

  function handleKeyUp(event: KeyboardEvent) {
    if (event.code === "Space") {
      modifierKeys.value.spaceKey = false
      updateCursor()
    }
    if (!event.altKey && modifierKeys.value.altKey) {
      modifierKeys.value.altKey = false
      updateCursor()
    }
  }

  // Mouse down handler to start panning
  function handleMouseDown(event: MouseEvent) {
    if (!containerRef.value)
      return

    // Only pan with left mouse button
    if (event.button !== 0)
      return

    // Check if we should enable panning
    const shouldPan = isDraggable.value

    if (!shouldPan)
      return

    // Don't pan if clicking on interactive elements
    const target = event.target as HTMLElement
    if (target.tagName === "BUTTON" || target.closest("button"))
      return

    event.preventDefault()

    // Disable smooth scrolling to prevent lag during panning
    disableSmoothScroll()

    panState.value = {
      isPanning: true,
      startX: event.clientX,
      startY: event.clientY,
      scrollStartX: containerRef.value.scrollLeft,
      scrollStartY: containerRef.value.scrollTop,
      displayHint: panState.value.displayHint,
    }

    containerRef.value.style.cursor = "grabbing"
    console.log("Started panning at", event.clientX, event.clientY, {
      scale: scale.value,
      altKey: modifierKeys.value.altKey,
      spaceKey: modifierKeys.value.spaceKey,
    })
  }

  // Mouse move handler for panning
  function handleMouseMove(event: MouseEvent) {
    if (!containerRef.value || !panState.value.isPanning)
      return

    event.preventDefault()

    const deltaX = panState.value.startX - event.clientX
    const deltaY = panState.value.startY - event.clientY

    // Direct scroll manipulation for smooth panning
    containerRef.value.scrollLeft = panState.value.scrollStartX + deltaX
    containerRef.value.scrollTop = panState.value.scrollStartY + deltaY
  }

  // Mouse up handler to stop panning
  function handleMouseUp() {
    if (!containerRef.value || !panState.value.isPanning)
      return

    panState.value.isPanning = false

    // Restore smooth scrolling after panning
    restoreSmoothScroll()

    updateCursor()
    console.log("Stopped panning")
  }

  // Mouse enter/leave handlers to update cursor based on modifier keys
  function handleMouseEnter() {
    updateCursor()
  }

  function handleMouseLeave() {
    if (!panState.value.isPanning && containerRef.value) {
      containerRef.value.style.cursor = ""
    }
  }

  // Double-click handler for zoom
  function handleDoubleClick(event: MouseEvent) {
    if (!containerRef.value)
      return

    event.preventDefault()

    const rect = containerRef.value.getBoundingClientRect()
    const clientX = event.clientX - rect.left
    const clientY = event.clientY - rect.top

    // Toggle between fit-to-width and 100% zoom
    const newScale = scale.value <= 1.0 ? 2.0 : 1.0
    console.log(`Double-click zoom: ${scale.value.toFixed(2)} -> ${newScale.toFixed(2)}`)
    onZoomChange(newScale, clientX, clientY)
  }

  // Touch handlers for mobile support
  let touchStartDistance = 0
  let touchStartScale = 1

  function handleTouchStart(event: TouchEvent) {
    if (!containerRef.value)
      return

    if (event.touches.length === 2) {
      // Pinch to zoom
      const touch1 = event.touches[0]
      const touch2 = event.touches[1]
      touchStartDistance = Math.hypot(
        touch2.clientX - touch1.clientX,
        touch2.clientY - touch1.clientY,
      )
      touchStartScale = scale.value
      event.preventDefault()
    }
    else if (event.touches.length === 1 && isDraggable.value) {
      // Touch pan
      const touch = event.touches[0]
      panState.value = {
        isPanning: true,
        startX: touch.clientX,
        startY: touch.clientY,
        scrollStartX: containerRef.value.scrollLeft,
        scrollStartY: containerRef.value.scrollTop,
        displayHint: panState.value.displayHint,
      }
    }
  }

  function handleTouchMove(event: TouchEvent) {
    if (!containerRef.value)
      return

    if (event.touches.length === 2) {
      // Pinch zoom
      const touch1 = event.touches[0]
      const touch2 = event.touches[1]
      const currentDistance = Math.hypot(
        touch2.clientX - touch1.clientX,
        touch2.clientY - touch1.clientY,
      )

      if (touchStartDistance > 0) {
        const zoomRatio = currentDistance / touchStartDistance
        const newScale = Math.max(0.25, Math.min(touchStartScale * zoomRatio, 5.0))

        // Use center of the two touches as zoom center
        const centerX = (touch1.clientX + touch2.clientX) / 2
        const centerY = (touch1.clientY + touch2.clientY) / 2
        const rect = containerRef.value.getBoundingClientRect()

        onZoomChange(newScale, centerX - rect.left, centerY - rect.top)
      }
      event.preventDefault()
    }
    else if (event.touches.length === 1 && panState.value.isPanning) {
      // Touch pan
      const touch = event.touches[0]
      const deltaX = panState.value.startX - touch.clientX
      const deltaY = panState.value.startY - touch.clientY

      containerRef.value.scrollLeft = panState.value.scrollStartX + deltaX
      containerRef.value.scrollTop = panState.value.scrollStartY + deltaY
      event.preventDefault()
    }
  }

  function handleTouchEnd() {
    panState.value.isPanning = false
    touchStartDistance = 0
    touchStartScale = 1
  }

  // Update cursor style based on zoom level and modifier keys
  function updateCursor() {
    if (!containerRef.value)
      return

    if (panState.value.isPanning) {
      containerRef.value.style.cursor = "grabbing"
    }
    else if (isDraggable.value) {
      containerRef.value.style.cursor = "grab"
    }
    else {
      containerRef.value.style.cursor = ""
    }
  }

  // Setup event listeners
  function setupEventListeners() {
    if (!containerRef.value)
      return

    const container = containerRef.value

    // Mouse events
    useEventListener(container, "wheel", handleWheel, { passive: false })
    useEventListener(container, "mousedown", handleMouseDown)
    useEventListener(document, "mousemove", handleMouseMove)
    useEventListener(document, "mouseup", handleMouseUp)
    useEventListener(container, "dblclick", handleDoubleClick)
    useEventListener(container, "mouseenter", handleMouseEnter)
    useEventListener(container, "mouseleave", handleMouseLeave)

    // Keyboard events
    useEventListener(document, "keydown", handleKeyDown)
    useEventListener(document, "keyup", handleKeyUp)

    // Touch events
    useEventListener(container, "touchstart", handleTouchStart, { passive: false })
    useEventListener(container, "touchmove", handleTouchMove, { passive: false })
    useEventListener(container, "touchend", handleTouchEnd)

    // Update cursor on zoom changes
    updateCursor()
  }

  // Cleanup function
  function cleanup() {
    if (containerRef.value) {
      containerRef.value.style.cursor = ""
      containerRef.value.style.scrollBehavior = ""
    }
    panState.value.isPanning = false
    modifierKeys.value = {
      altKey: false,
      spaceKey: false,
    }
  }

  return {
    panState,
    isDraggable,
    setupEventListeners,
    updateCursor,
    cleanup,
  }
}

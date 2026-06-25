import { ref, type Ref } from "vue"

export function usePdfZoom() {
  const scale = ref(1.0)

  function zoomIn() {
    scale.value = Math.min(scale.value * 1.25, 5.0)
  }

  function zoomOut() {
    scale.value = Math.max(scale.value / 1.25, 0.25)
  }

  function setScale(newScale: number) {
    scale.value = Math.max(0.25, Math.min(newScale, 5.0))
  }

  function resetZoom() {
    scale.value = 1.0
  }

  // Zoom to a specific point while maintaining that point's position
  function zoomToPoint(
    newScale: number,
    containerRef: Ref<HTMLElement | undefined>,
    clientX: number,
    clientY: number,
  ) {
    if (!containerRef.value) {
      setScale(newScale)
      return
    }

    const container = containerRef.value
    const oldScale = scale.value

    // Calculate scroll position before zoom
    const scrollLeft = container.scrollLeft
    const scrollTop = container.scrollTop

    // Calculate the point relative to the scrollable content
    const pointX = scrollLeft + clientX
    const pointY = scrollTop + clientY

    // Apply the new scale
    setScale(newScale)

    // Calculate the new position of the point after zoom
    const scaleFactor = newScale / oldScale
    const newPointX = pointX * scaleFactor
    const newPointY = pointY * scaleFactor

    // Adjust scroll position to keep the point under the cursor
    const newScrollLeft = newPointX - clientX
    const newScrollTop = newPointY - clientY

    console.log(`Zoom to point: scale ${oldScale.toFixed(2)} -> ${newScale.toFixed(2)}, cursor (${clientX}, ${clientY})`)
    console.log(`Scroll adjust: (${scrollLeft}, ${scrollTop}) -> (${newScrollLeft}, ${newScrollTop})`)

    // Set the new scroll position after the next render
    requestAnimationFrame(() => {
      if (container) {
        container.scrollLeft = newScrollLeft
        container.scrollTop = newScrollTop
      }
    })
  }

  return {
    scale,
    zoomIn,
    zoomOut,
    setScale,
    resetZoom,
    zoomToPoint,
  }
}

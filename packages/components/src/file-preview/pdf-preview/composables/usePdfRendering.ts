import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist"
import { useBoolean } from "@airalogy/composables"
import { ref, type Ref, shallowRef } from "vue"

export function usePdfRendering(
  pdfDocument: Ref<PDFDocumentProxy | null>,
  scale: Ref<number>,
) {
  const { bool: isRendering, setTrue: startRendering, setFalse: endRendering } = useBoolean(false)
  const currentPageProxy = shallowRef<PDFPageProxy | null>(null)
  const currentRenderTask = shallowRef<any>(null)
  const canvasRef = ref<HTMLCanvasElement>()

  async function renderPage(pageNumber: number) {
    if (!pdfDocument.value || !canvasRef.value)
      return

    // Cancel any existing render task
    if (currentRenderTask.value) {
      console.log("Cancelling previous render task")
      currentRenderTask.value.cancel()
      currentRenderTask.value = null
    }

    // Prevent concurrent renders
    if (isRendering.value) {
      console.log("Render already in progress, skipping")
      return
    }

    startRendering()
    console.log(`Starting render for page ${pageNumber} at scale ${scale.value}`)

    try {
      // Get page
      currentPageProxy.value = await pdfDocument.value.getPage(pageNumber)
      const viewport = currentPageProxy.value.getViewport({ scale: scale.value })

      // Set canvas dimensions
      const canvas = canvasRef.value
      const context = canvas.getContext("2d")
      if (!context) {
        endRendering()
        return
      }

      canvas.height = viewport.height
      canvas.width = viewport.width

      // Render page
      const renderContext = {
        canvasContext: context,
        viewport,
      }

      // Store the render task so we can cancel it if needed
      const renderTask = currentPageProxy.value.render(renderContext)
      currentRenderTask.value = renderTask

      await renderTask.promise
      console.log(`Successfully rendered page ${pageNumber}`)
    }
    catch (err) {
      // Handle expected cancellation errors gracefully
      if (err instanceof Error && err.name === "RenderingCancelledException") {
        console.log("Render was cancelled (expected)")
        return
      }

      console.error("Error rendering page:", err)
      throw err
    }
    finally {
      endRendering()
      currentRenderTask.value = null
    }
  }

  async function fitToWidth(containerRef: Ref<HTMLElement | undefined>) {
    if (!pdfDocument.value || !containerRef.value)
      return

    if (isRendering.value) {
      console.log("Fit to width skipped - render in progress")
      return
    }

    const containerWidth = containerRef.value.clientWidth - 32 // Account for padding

    // Get a page proxy to calculate viewport (use page 1 as reference)
    const pageProxy = await pdfDocument.value.getPage(1)
    const viewport = pageProxy.getViewport({ scale: 1.0 })
    const newScale = containerWidth / viewport.width

    scale.value = Math.max(0.25, Math.min(newScale, 5.0))
  }

  async function fitToHeight(containerRef: Ref<HTMLElement | undefined>) {
    if (!pdfDocument.value || !containerRef.value)
      return

    if (isRendering.value) {
      console.log("Fit to height skipped - render in progress")
      return
    }

    const containerHeight = containerRef.value.clientHeight - 120 // Account for padding and floating controls

    // Get a page proxy to calculate viewport (use page 1 as reference)
    const pageProxy = await pdfDocument.value.getPage(1)
    const viewport = pageProxy.getViewport({ scale: 1.0 })
    const newScale = containerHeight / viewport.height

    scale.value = Math.max(0.25, Math.min(newScale, 5.0))
  }

  function cleanup() {
    if (currentRenderTask.value) {
      console.log("Cleaning up render task")
      currentRenderTask.value.cancel()
      currentRenderTask.value = null
      endRendering()
    }
  }

  return {
    isRendering,
    canvasRef,
    renderPage,
    fitToWidth,
    fitToHeight,
    cleanup,
  }
}

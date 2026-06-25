<template>
  <div ref="parentWrapperRef" class="embed-pdf-main">
    <div ref="pdfWrapperRef" class="embed-pdf" />
  </div>
</template>

<script lang="ts" setup>
import type { DocumentInitParameters, PDFDataRangeTransport, PDFDocumentLoadingTask, PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist/types/src/display/api"

import type { PageViewport } from "pdfjs-dist/types/src/display/display_utils"
import * as pdfjsLib from "pdfjs-dist/legacy/build/pdf.min.mjs"
import { EventBus, PDFViewer } from "pdfjs-dist/legacy/web/pdf_viewer.mjs"
import "pdfjs-dist/legacy/web/pdf_viewer.css"

interface VuePdfPropsType {
  /**
   * The source of the pdf. Accepts the following types `string | URL | Uint8Array | PDFDataRangeTransport | DocumentInitParameters`
   */
  src: string | URL | Uint8Array | PDFDataRangeTransport | DocumentInitParameters
  /**
   * The page number of the pdf to display.
   */
  page?: number
  /**
   * The scale (zoom) of the pdf. Setting this will also disable auto scaling and resizing.
   */
  scale?: number
  /**
   * Whether to enable text selection
   */
  enableTextSelection?: boolean
  /**
   * Whether to enable annotations (clickable links)
   */
  enableAnnotations?: boolean
}

defineOptions({ name: "EmbedPdf" })
const props = defineProps<VuePdfPropsType>()
const emit = defineEmits<IEmits>()

interface IEmits {
  (e: "pdfLoaded", pdf: PDFDocumentProxy): void
  (e: "pageRendered", pageNumber: number): void
  (e: "pdfError"): void
  (e: "totalPages", numberOfPages: number): void
  (e: "pageChanged", pageNumber: number): void
  (e: "scaleChanged", scale: number): void
  (e: "textSelectionChanged", textSelection: string): void
}

function createLoadingTask(src: string | URL | Uint8Array | PDFDataRangeTransport | DocumentInitParameters): PDFDocumentLoadingTask {
  const loadingTask = pdfjsLib.getDocument(src)
  return loadingTask
}

const loading = ref<boolean>(false)

const pdfWrapperRef = ref<HTMLDivElement | null>(null)
const parentWrapperRef = ref<HTMLDivElement | null>(null)

const thePDF = ref<PDFDocumentProxy | null>(null)
const numberOfPages = ref<number>(0)

const eventBus = ref<EventBus | null>(null)

const pageNumber = computed(() => props.page || 1)
const pdfjsViewer = ref<PDFViewer | null>(null)

function initPdfWorker() {
  loading.value = true
  pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
    "pdfjs-dist/legacy/build/pdf.worker.min.mjs",
    import.meta.url,
  ).toString()

  const loadingTask = createLoadingTask(props.src)

  if (!eventBus.value) {
    eventBus.value = new EventBus()
  }

  const pdfWrapperEl = pdfWrapperRef.value as HTMLDivElement
  pdfjsViewer.value = new PDFViewer({
    container: pdfWrapperEl,
    eventBus: eventBus.value as EventBus,
  })

  loadingTask.promise.then((pdf: PDFDocumentProxy) => {
    emit("pdfLoaded", pdf)
    thePDF.value = pdf
    numberOfPages.value = pdf.numPages
    emit("totalPages", numberOfPages.value)
    if (pageNumber.value <= numberOfPages.value) {
      pdf.getPage(pageNumber.value).then((page: PDFPageProxy) => renderPage(page))
    }
  })
}

async function renderPage(page: PDFPageProxy) {
  loading.value = true

  const pdfWrapperEl = pdfWrapperRef.value!
  const parentWrapperEl = parentWrapperRef.value!

  // Create a wrapper for each page
  const pageWrapper = document.createElement("div")
  pageWrapper.classList.add("embed-pdf__wrapper")
  pageWrapper.id = `embed-pdf-page-${props.page}`

  // Create a canvas element for each page to draw on
  const canvas = document.createElement("canvas")
  pageWrapper.appendChild(canvas)

  // Create an annotation layer for each page
  const annotationLayer = document.createElement("div")
  if (props.enableAnnotations) {
    annotationLayer.classList.add("embed-pdf__wrapper-annotation-layer")
    pageWrapper.appendChild(annotationLayer)
  }

  // Create div which will hold text-fragments (for selection)
  const textLayerDiv = document.createElement("div")
  if (props.enableTextSelection) {
    textLayerDiv.classList.add("textLayer", "embed-pdf__wrapper-text-layer")
    pageWrapper.appendChild(textLayerDiv)
  }

  pdfWrapperEl?.appendChild(pageWrapper)

  // This gives us the page's dimensions at full scale
  const initViewport = page.getViewport({ scale: 1 })

  const context = canvas.getContext("2d")
  await scaleCanvas(
    pdfWrapperEl,
    initViewport,
    page,
    canvas,
    context,
    textLayerDiv,
    annotationLayer,
  )

  if (!props.scale) {
    const debouncedScaling = useDebounceFn(
      async () =>
        await scaleCanvas(
          pdfWrapperEl,
          initViewport,
          page,
          canvas,
          context,
          textLayerDiv,
          annotationLayer,
        ),
      300,
    )
    window.addEventListener("resize", debouncedScaling)
  }
  else {
    parentWrapperEl.style.display = "inline-block"
    pdfWrapperEl.style.display = "inline-block"
  }
}

async function scaleCanvas(pdfWrapperEl: HTMLElement, initializedViewport: PageViewport, page: PDFPageProxy, canvas: HTMLCanvasElement, context: any, textLayerDiv: HTMLDivElement, annotationLayer: HTMLDivElement) {
  textLayerDiv.innerHTML = ""
  annotationLayer.innerHTML = ""

  const pdfWrapperElStyles = window.getComputedStyle(pdfWrapperEl)
  const pdfWrapperElWidth = Number.parseFloat(pdfWrapperElStyles.width)

  const scale = props.scale ? props.scale : pdfWrapperElWidth / initializedViewport.width
  const viewport = page.getViewport({ scale })

  // assume the device pixel ratio is 1 if the browser doesn't specify it
  const devicePixelRatio = window.devicePixelRatio || 1

  // determine the 'backing store ratio' of the canvas context
  const backingStoreRatio
    = context.webkitBackingStorePixelRatio
    || context.mozBackingStorePixelRatio
    || context.msBackingStorePixelRatio
    || context.oBackingStorePixelRatio
    || context.backingStorePixelRatio
    || 1

  // determine the actual ratio we want to draw at
  const ratio = devicePixelRatio / backingStoreRatio

  if (devicePixelRatio !== backingStoreRatio) {
    // set the 'real' canvas size to the higher width/height
    canvas.width = props.scale ? viewport.width * ratio : pdfWrapperElWidth * ratio
    canvas.height = viewport.height * ratio

    // ...then scale it back down with CSS
    canvas.style.width = props.scale ? "" : "100%"
    canvas.style.height = `${viewport.height}px`
  }
  else {
    // this is a normal 1:1 device; just scale it simply
    canvas.width = props.scale ? viewport.width : pdfWrapperElWidth
    canvas.height = viewport.height
    canvas.style.width = ""
    canvas.style.height = ""
  }

  // scale the drawing context so everything will work at the higher ratio
  await context.scale(ratio, ratio)
  // Draw it on the canvas
  if (context) {
    page.render({ canvasContext: context, viewport }).promise.then(() => {
      // Render text layer for text selection
      if (props.enableTextSelection) {
        page.getTextContent().then((textContent) => {
          // Create new instance of TextLayerBuilder class
          const pageView = pdfjsViewer.value?.getPageView?.(page._pageIndex)

          if (pageView) {
            pageView.draw()
          }
          // // Set text-fragments
          // textLayer.setTextContent(textContent)
          // emit("textContent", textContent)
          // // Render text-fragments
          // textLayer.render()
        })
      }

      if (props.enableAnnotations) {
        // Render annotation layer for clickable links
        page.getAnnotations().then((annotationData) => {
          annotationLayer.style.cssText = `left: 0; top: 0; height: ${viewport.height}px; width: ${
            props.scale ? viewport.width : pdfWrapperElWidth
          }px;`

          // Render the annotation layer
          //   pdfjsLib.AnnotationLayer.render({
          //     viewport: viewport.clone({ dontFlip: true }),
          //     div: annotationLayer,
          //     annotations: annotationData,
          //     page: page,
          //     linkService: "",
          //     downloadManager: "",
          //     renderInteractiveForms: false,
          //   })
        })
      }
      loading.value = false
    })
  }
}

onMounted(() => {
  initPdfWorker()
})

defineExpose({
  pdfWrapperRef,
  parentWrapperRef,
})
</script>

<style lang="sass">
.embed-pdf
  &__wrapper
    position: relative

    &-text-layer
      br
        display: none

    &-annotation-layer
      position: absolute
      .linkAnnotation
        position: absolute
        z-index: 1
        a
          width: 100%
          height: 100%
          display: inline-block
</style>

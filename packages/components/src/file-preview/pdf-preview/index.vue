<template>
  <n-spin size="large" :show="loading" class="relative" content-class="size-full">
    <template #description>
      {{ description }}
    </template>
    <!-- PDF Content - Now takes full height -->
    <div
      ref="containerRef"
      class="size-full select-none overflow-auto rounded-md bg-gray-100 outline-none"
      style="scroll-behavior: smooth;"
      tabindex="0"
      @focus="isContainerFocused = true"
      @blur="isContainerFocused = false"
      @mouseenter="isMouseOver = true"
      @mouseleave="isMouseOver = false"
    >
      <!-- Error State -->
      <div v-if="error" class="h-full flex flex-col items-center justify-center text-red-500">
        <n-icon size="64" class="mb-4">
          <icon-ion-warning-outline />
        </n-icon>
        <p class="mb-2 text-lg font-medium">
          Failed to Load PDF
        </p>
        <p class="mb-4 text-center text-sm text-gray-500">
          {{ error }}
        </p>
        <n-button @click="retryLoad">
          <template #icon>
            <n-icon><icon-ion-refresh /></n-icon>
          </template>
          Retry
        </n-button>
      </div>

      <!-- Multi-Page Scroll Mode -->
      <div v-if="scrollToLoad && !error" class="flex flex-col items-center gap-4 p-4">
        <pdf-page
          v-for="pageNum in scrollMode.pagesToShow.value"
          :key="`page-${pageNum}`"
          :page-number="pageNum"
          :page-width="scrollMode.getPageWidth(pageNum)"
          :page-height="scrollMode.getPageHeight(pageNum)"
          :is-loaded="scrollMode.isPageLoaded(pageNum)"
          :is-loading="scrollMode.isPageLoading(pageNum)"
          :set-page-ref="scrollMode.setPageRef"
          :set-canvas-ref="scrollMode.setCanvasRef"
        />

        <!-- Show "more pages" indicator if we're not showing all pages -->
        <div v-if="props.pagesOverview > 0 && totalPages > props.pagesOverview && !scrollMode.showingAllPages.value" class="mt-4 text-center text-sm text-gray-500">
          Showing {{ props.pagesOverview }} of {{ totalPages }} pages
          <br>
          <n-button size="small" text @click="scrollMode.showAllPages">
            Show All Pages
          </n-button>
        </div>
      </div>

      <!-- Single Page Mode -->
      <div v-else-if="!scrollToLoad && !error" class="flex justify-center p-4">
        <canvas ref="canvasRef" />
      </div>
    </div>

    <!-- Floating Controls -->
    <pdf-actions
      :current-page="currentPage"
      :total-pages="totalPages"
      :scale="scale"
      :can-go-to-previous="canGoToPrevious"
      :can-go-to-next="canGoToNext"
      :loading="loading"
      :page-input-value="pageInputValue"
      @previous-page="handlePreviousPage"
      @next-page="handleNextPage"
      @zoom-in="handleZoomIn"
      @zoom-out="handleZoomOut"
      @fit-to-width="handleFitToWidth"
      @fit-to-height="handleFitToHeight"
      @page-input="handlePageInput"
    />

    <!-- Grab Mode Hint -->
    <div
      v-if="!loading && !error && scale <= 1.0 && !panState.isPanning && panState.displayHint"
      class="absolute bottom-4 right-4 rounded bg-black/70 px-2 py-1 text-xs text-white opacity-60 backdrop-blur-sm transition-opacity hover:opacity-80"
    >
      Hold <kbd class="rounded bg-white/20 px-1">Alt</kbd> to grab & pan
      <n-button size="tiny" quaternary :theme-overrides="{ colorQuaternary: 'white' }" @click="panState.displayHint = !panState.displayHint">
        {{ panState.displayHint ? "Hide" : "Show" }}
      </n-button>
    </div>
  </n-spin>
</template>

<script setup lang="ts">
import { useEventListener } from "@vueuse/core"
import IconIonRefresh from "~icons/ion/refresh"
import IconIonWarningOutline from "~icons/ion/warning-outline"
import { NButton, NIcon, NSpin } from "naive-ui"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { usePdfDocument } from "./composables/usePdfDocument"
import { usePdfInteractions } from "./composables/usePdfInteractions"
import { usePdfNavigation } from "./composables/usePdfNavigation"
import { usePdfRendering } from "./composables/usePdfRendering"
import { usePdfScrollMode } from "./composables/usePdfScrollMode"
import { usePdfZoom } from "./composables/usePdfZoom"
import PdfActions from "./modules/pdf-actions.vue"
import PdfPage from "./modules/pdf-page.vue"
import "pdfjs-dist/legacy/web/pdf_viewer.css"

interface IProps {
  pdfUrl: string
  scrollToLoad?: boolean
  pagesOverview?: number
  loading?: boolean
  error?: string
  description?: string
}

const props = withDefaults(defineProps<IProps>(), {
  scrollToLoad: false,
  pagesOverview: 0, // 0 means show all pages
  loading: false,
  error: "",
  description: "",
})

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "retryLoad"): void
}
const containerRef = ref<HTMLElement>()

// Focus and mouse state
const isContainerFocused = ref(false)
const isMouseOver = ref(false)

// Initialize composables
const { loading, error, pdfDocument, totalPages, loadPdf, cleanup: cleanupDocument } = usePdfDocument(props)

const { currentPage, canGoToPrevious, canGoToNext, pageInputValue, goToPreviousPage, goToNextPage } = usePdfNavigation(totalPages)
const { scale, zoomIn, zoomOut, zoomToPoint } = usePdfZoom()

const scrollMode = usePdfScrollMode(
  containerRef,
  pdfDocument,
  scale,
  currentPage,
  totalPages,
  props.pagesOverview,
)

const { renderPage, isRendering, fitToWidth, fitToHeight, canvasRef, cleanup: cleanupRendering } = usePdfRendering(pdfDocument, scale)

// Handle zoom with cursor position tracking
function handleZoomChange(newScale: number, clientX?: number, clientY?: number) {
  if (isRendering.value) {
    console.log("Zoom change skipped - render in progress")
    return
  }

  if (clientX !== undefined && clientY !== undefined) {
    // Zoom to specific point (for wheel/touch zoom)
    zoomToPoint(newScale, containerRef, clientX, clientY)
  }
  else {
    // Regular zoom (for button clicks)
    scale.value = newScale
  }

  // Re-render or reload pages after zoom
  if (props.scrollToLoad) {
    scrollMode.reloadVisiblePages()
  }
  else {
    renderPage(currentPage.value)
  }
}

// Initialize interactions
const { panState, updateCursor, setupEventListeners, cleanup: cleanupInteractions } = usePdfInteractions(
  containerRef,
  scale,
  props.scrollToLoad,
  handleZoomChange,
)

// Watch for URL changes
watch(() => props.pdfUrl, () => {
  cleanup()
  loadPdf(props.pdfUrl)
}, { immediate: true })

// Watch for scroll mode changes
watch(() => props.scrollToLoad, (newScrollToLoad) => {
  if (pdfDocument.value) {
    if (newScrollToLoad) {
      scrollMode.setupScrollMode()
    }
    else {
      scrollMode.cleanupScrollMode()
      renderPage(currentPage.value)
    }
  }
})

// Watch for page changes in single-page mode
watch(currentPage, (newPage) => {
  if (!props.scrollToLoad) {
    renderPage(newPage)
  }
})

// Event handlers
function handlePreviousPage() {
  goToPreviousPage()
  if (props.scrollToLoad) {
    scrollMode.scrollToPageElement(currentPage.value)
  }
}

function handleNextPage() {
  goToNextPage()
  if (props.scrollToLoad) {
    scrollMode.scrollToPageElement(currentPage.value)
  }
}

function handleZoomIn() {
  if (isRendering.value) {
    console.log("Zoom in skipped - render in progress")
    return
  }
  zoomIn()

  if (props.scrollToLoad) {
    scrollMode.reloadVisiblePages()
  }
  else {
    renderPage(currentPage.value)
  }
}

function handleZoomOut() {
  if (isRendering.value) {
    console.log("Zoom out skipped - render in progress")
    return
  }
  zoomOut()

  if (props.scrollToLoad) {
    scrollMode.reloadVisiblePages()
  }
  else {
    renderPage(currentPage.value)
  }
}

async function handleFitToWidth() {
  await fitToWidth(containerRef)

  if (props.scrollToLoad) {
    scrollMode.reloadVisiblePages()
  }
  else {
    renderPage(currentPage.value)
  }
}

async function handleFitToHeight() {
  await fitToHeight(containerRef)

  if (props.scrollToLoad) {
    scrollMode.reloadVisiblePages()
  }
  else {
    renderPage(currentPage.value)
  }
}

function handlePageInput(value: string) {
  const pageNum = Number.parseInt(value, 10)
  if (pageNum && pageNum >= 1 && pageNum <= totalPages.value) {
    currentPage.value = pageNum
    if (props.scrollToLoad) {
      scrollMode.scrollToPageElement(pageNum)
    }
  }
  else {
    // Reset to current page if invalid
    pageInputValue.value = currentPage.value.toString()
  }
}

function retryLoad() {
  if (props.pdfUrl) {
    loadPdf(props.pdfUrl)
  }
  emit("retryLoad")
}

// Keyboard shortcuts
function handleKeydown(event: KeyboardEvent) {
  // Only handle keyboard events if container is focused or mouse is over it
  if (!isContainerFocused.value && !isMouseOver.value) {
    return
  }

  switch (event.key) {
    case "ArrowLeft":
      if (canGoToPrevious.value) {
        handlePreviousPage()
        event.preventDefault()
      }
      break
    case "ArrowRight":
      if (canGoToNext.value) {
        handleNextPage()
        event.preventDefault()
      }
      break
    case "+":
    case "=":
      handleZoomIn()
      event.preventDefault()
      break
    case "-":
      handleZoomOut()
      event.preventDefault()
      break
  }
}

// Cleanup function
function cleanup() {
  cleanupRendering()
  scrollMode.cleanupScrollMode()
  cleanupDocument()
  cleanupInteractions()
}

const description = computed(() => {
  if (props.description) {
    return props.description
  }
  if (loading.value)
    return "Loading PDF..."
  if (error.value) {
    return "Failed to load PDF"
  }
  return ""
})

// Setup PDF on load
async function setupPdf() {
  if (props.scrollToLoad) {
    await scrollMode.setupScrollMode()
  }
  else {
    await renderPage(1)
  }
}

// Watch for PDF document load
watch(pdfDocument, async () => {
  if (pdfDocument.value) {
    await setupPdf()
    // Setup interactions after PDF is loaded
    setupEventListeners()
  }
})

// Watch for scale changes to update cursor
watch(scale, () => {
  updateCursor()
})

// Lifecycle
useEventListener(document, "keydown", handleKeydown)
onBeforeUnmount(cleanup)
</script>

<style scoped lang="sass">
/* Prevent text selection while dragging */
.pdf-container
  user-select: none
  -webkit-user-select: none
  -moz-user-select: none
  -ms-user-select: none

/* Improve smooth scrolling */
.pdf-container
  scroll-behavior: smooth

/* Custom scrollbar styling */
.pdf-container::-webkit-scrollbar
  width: 8px
  height: 8px

.pdf-container::-webkit-scrollbar-track
  background: rgba(0, 0, 0, 0.1)
  border-radius: 4px

.pdf-container::-webkit-scrollbar-thumb
  background: rgba(0, 0, 0, 0.3)
  border-radius: 4px

.pdf-container::-webkit-scrollbar-thumb:hover
  background: rgba(0, 0, 0, 0.5)
</style>

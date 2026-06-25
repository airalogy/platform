import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist"
import { useScroll } from "@vueuse/core"
import { computed, nextTick, ref, type Ref, watch } from "vue"

interface PageData {
  proxy: PDFPageProxy | null
  loaded: boolean
  loading: boolean
  width: number
  height: number
}

export function usePdfScrollMode(
  containerRef: Ref<HTMLElement | undefined>,
  pdfDocument: Ref<PDFDocumentProxy | null> | Readonly<Ref<PDFDocumentProxy | null>>,
  scale: Ref<number>,
  currentPage: Ref<number>,
  totalPages: Ref<number>,
  pagesOverview: number,
) {
  const pageElements = new Map<number, HTMLElement>()
  const pageCanvases = new Map<number, HTMLCanvasElement>()
  const loadedPages = ref<Record<number, PageData>>({})
  const intersectionObserver = ref<IntersectionObserver | null>(null)
  const visiblePages = ref<Set<number>>(new Set())
  const showingAllPages = ref(false)
  const isProgrammaticScrolling = ref(false)

  // Use VueUse's useScroll to track scrolling state
  const { isScrolling } = useScroll(containerRef, {
    throttle: 100,
  })

  const pagesToShow = computed(() => {
    if (showingAllPages.value)
      return totalPages.value
    return pagesOverview > 0 ? Math.min(pagesOverview, totalPages.value) : totalPages.value
  })

  const currentlyLoadingPage = computed(() => {
    for (const [pageNum, pageData] of Object.entries(loadedPages.value)) {
      if (pageData.loading) {
        return Number(pageNum)
      }
    }
    return null
  })

  const loadingDescription = computed(() => {
    const pageNum = currentlyLoadingPage.value
    return pageNum ? `Loading page ${pageNum}...` : "Loading..."
  })

  // Helper functions
  function setPageRef(el: any, pageNum: number) {
    if (el) {
      pageElements.set(pageNum, el)
    }
  }

  function setCanvasRef(el: any, pageNum: number) {
    if (el) {
      pageCanvases.set(pageNum, el)
    }
  }

  function isPageLoaded(pageNum: number): boolean {
    return loadedPages.value[pageNum]?.loaded ?? false
  }

  function isPageLoading(pageNum: number): boolean {
    return currentlyLoadingPage.value === pageNum
  }

  function getPageHeight(pageNum: number): number {
    const pageData = loadedPages.value[pageNum]
    if (pageData?.height) {
      return pageData.height
    }
    // Estimate height based on scale (A4 proportions)
    return Math.round(842 * scale.value)
  }

  function getPageWidth(pageNum: number): number {
    const pageData = loadedPages.value[pageNum]
    if (pageData?.width) {
      return pageData.width
    }
    // Estimate width based on scale (A4 proportions)
    return Math.round(595 * scale.value)
  }

  function getPageNumberFromElement(element: HTMLElement): number {
    const allElements = Array.from(pageElements.values())
    const index = allElements.indexOf(element)
    return index + 1
  }

  function scrollToPageElement(pageNum: number) {
    if (!containerRef.value)
      return

    const pageElement = pageElements.get(pageNum)
    if (pageElement) {
      isProgrammaticScrolling.value = true

      pageElement.scrollIntoView({ behavior: "smooth", block: "start" })

      const stopWatching = watch(isScrolling, (scrolling) => {
        if (!scrolling && isProgrammaticScrolling.value) {
          isProgrammaticScrolling.value = false
          stopWatching()
        }
      })
    }
  }

  async function setupScrollMode() {
    if (!pdfDocument.value)
      return

    loadedPages.value = {}
    for (let i = 1; i <= pagesToShow.value; i++) {
      loadedPages.value[i] = {
        proxy: null,
        loaded: false,
        loading: false,
        width: getPageWidth(i),
        height: getPageHeight(i),
      }
    }

    await nextTick()

    setTimeout(() => {
      setupIntersectionObserver()
    }, 100)

    await loadPageInScrollMode(1)
  }

  function setupIntersectionObserver() {
    if (intersectionObserver.value) {
      intersectionObserver.value.disconnect()
    }

    intersectionObserver.value = new IntersectionObserver(
      handleIntersection,
      {
        root: containerRef.value,
        rootMargin: "200px",
        threshold: 0.1,
      },
    )

    pageElements.forEach((element) => {
      if (element && intersectionObserver.value) {
        intersectionObserver.value.observe(element)
      }
    })
  }

  function handleIntersection(entries: IntersectionObserverEntry[]) {
    for (const entry of entries) {
      const pageElement = entry.target as HTMLElement
      const pageNum = getPageNumberFromElement(pageElement)

      if (entry.isIntersecting) {
        visiblePages.value.add(pageNum)
        loadPageInScrollMode(pageNum)

        if (pageNum > 1)
          loadPageInScrollMode(pageNum - 1)
        if (pageNum < totalPages.value)
          loadPageInScrollMode(pageNum + 1)
      }
      else {
        visiblePages.value.delete(pageNum)
      }
    }

    if (!isProgrammaticScrolling.value && visiblePages.value.size > 0) {
      currentPage.value = Math.min(...visiblePages.value)
    }

    unloadDistantPages()
  }

  async function loadPageInScrollMode(pageNum: number) {
    if (!pdfDocument.value || pageNum < 1 || pageNum > totalPages.value)
      return

    const pageData = loadedPages.value[pageNum]
    if (!pageData || pageData.loaded || pageData.loading)
      return

    console.log(`Starting to load page ${pageNum}`)
    pageData.loading = true

    try {
      const pageProxy = await pdfDocument.value.getPage(pageNum)
      const viewport = pageProxy.getViewport({ scale: scale.value })

      pageData.width = viewport.width
      pageData.height = viewport.height
      pageData.proxy = pageProxy

      await nextTick()

      const canvas = pageCanvases.get(pageNum)
      if (!canvas) {
        console.warn(`Canvas not found for page ${pageNum}`)
        pageData.loading = false
        return
      }

      const context = canvas.getContext("2d")
      if (!context) {
        console.warn(`Canvas context not available for page ${pageNum}`)
        pageData.loading = false
        return
      }

      canvas.width = viewport.width
      canvas.height = viewport.height

      const renderContext = {
        canvasContext: context,
        viewport,
      }

      await pageProxy.render(renderContext).promise

      pageData.loaded = true
      pageData.loading = false
      loadedPages.value = { ...loadedPages.value }

      console.log(`Successfully loaded page ${pageNum} in scroll mode`)
    }
    catch (err) {
      pageData.loading = false
      console.error(`Error loading page ${pageNum}:`, err)
    }
  }

  function unloadDistantPages() {
    if (visiblePages.value.size === 0)
      return

    const currentPageNum = Math.min(...visiblePages.value)
    const maxDistance = 3

    for (const [pageNum, pageData] of Object.entries(loadedPages.value)) {
      if (pageData.loaded && Math.abs(Number(pageNum) - currentPageNum) > maxDistance) {
        pageData.loaded = false
        pageData.proxy = null
        console.log(`Unloaded distant page ${pageNum}`)
      }
    }
  }

  async function reloadVisiblePages() {
    for (const pageData of Object.values(loadedPages.value)) {
      pageData.loaded = false
      pageData.loading = false
    }

    for (const pageNum of visiblePages.value) {
      await loadPageInScrollMode(pageNum)
    }
  }

  function showAllPages() {
    showingAllPages.value = true
    nextTick(() => {
      setupScrollMode()
    })
  }

  function cleanupScrollMode() {
    if (intersectionObserver.value) {
      intersectionObserver.value.disconnect()
      intersectionObserver.value = null
    }
    loadedPages.value = {}
    pageElements.clear()
    pageCanvases.clear()
    visiblePages.value.clear()
  }

  return {
    loadedPages,
    pagesToShow,
    showingAllPages,
    loadingDescription,
    setPageRef,
    setCanvasRef,
    isPageLoaded,
    isPageLoading,
    getPageHeight,
    getPageWidth,
    scrollToPageElement,
    setupScrollMode,
    reloadVisiblePages,
    showAllPages,
    cleanupScrollMode,
  }
}

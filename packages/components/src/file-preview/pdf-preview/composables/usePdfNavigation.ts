import { computed, ref, type Ref, watch } from "vue"

export function usePdfNavigation(totalPages: Ref<number>) {
  const currentPage = ref(1)
  const pageInputValue = ref("1")

  const canGoToPrevious = computed(() => currentPage.value > 1)
  const canGoToNext = computed(() => currentPage.value < totalPages.value)

  function goToPreviousPage() {
    if (canGoToPrevious.value) {
      currentPage.value--
    }
  }

  function goToNextPage() {
    if (canGoToNext.value) {
      currentPage.value++
    }
  }

  function goToPage(pageNum: number) {
    if (pageNum >= 1 && pageNum <= totalPages.value) {
      currentPage.value = pageNum
    }
  }

  function handlePageInput() {
    const pageNum = Number.parseInt(pageInputValue.value, 10)
    if (pageNum && pageNum >= 1 && pageNum <= totalPages.value) {
      currentPage.value = pageNum
    }
    else {
      // Reset to current page if invalid
      pageInputValue.value = currentPage.value.toString()
    }
  }

  // Watch for page changes to update input value
  watch(currentPage, (newPage) => {
    pageInputValue.value = newPage.toString()
  })

  return {
    currentPage,
    pageInputValue,
    canGoToPrevious,
    canGoToNext,
    goToPreviousPage,
    goToNextPage,
    goToPage,
    handlePageInput,
  }
}

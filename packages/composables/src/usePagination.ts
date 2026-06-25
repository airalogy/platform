import type { UseOffsetPaginationOptions } from "@vueuse/core"
import type { MaybeRef } from "vue"
import { useRouteQuery } from "@vueuse/router"

export interface PaginationPayload {
  currentPage: number
  currentPageSize: number
  [k: string]: any
}

export function usePagination<T, K extends PaginationPayload = PaginationPayload>(
  init: {
    options: UseOffsetPaginationOptions & { mutateRoute?: boolean }
    fetchData?: (payload: K) => Promise<T>
    disabled?: MaybeRef<boolean>
  },
) {
  const { options: { mutateRoute = true, ...opts }, fetchData, disabled } = init
  const prevPagination = ref<{
    page: number
    pageSize: number
  }>({
    page: Math.max(unref(opts.page) as number, 1),
    pageSize: (unref(opts.pageSize) as number) || 10,
  })

  const disabledRef = toRef(disabled || false)
  const currPageRef = mutateRoute
    ? useRouteQuery("page", opts?.page, {
      transform: v => typeof v === "undefined" ? 1 : Math.max(1, Number(v)),
    })
    : opts?.page

  function setTotal() {
    const totalVal = toValue(opts.total) || 0
    const pageSizeVal = toValue(opts.pageSize) || 10
    const defaultPageCount = Math.max(1, Math.ceil(totalVal / pageSizeVal))
    const pageVal = toValue(currPageRef) || 1

    if (defaultPageCount < pageVal) {
      return pageVal * pageSizeVal
    }

    return opts.total
  }

  const total: Ref<number> = toRef(setTotal() || 0)

  const { currentPage, currentPageSize, pageCount, isFirstPage, isLastPage, next, prev }
    = useOffsetPagination({
      ...opts,
      page: currPageRef,
      total,
      onPageChange,
      onPageSizeChange,
    })

  const wrappedFetchData = async (payload: any) => {
    if (typeof fetchData !== "function") {
      return
    }

    try {
      await fetchData(payload)
    }
    catch (e) {
      recoverPagination()
    }
  }

  const offset = computed(() => ({
    start: Math.max((currentPage.value - 1) * currentPageSize.value, 0),
    end: Math.min(currentPage.value * currentPageSize.value),
  }))
  function handlePageChange(page: number) {
    prevPagination.value.page = currentPage.value

    currentPage.value = page
  }

  function recoverPagination() {
    const { page, pageSize } = prevPagination.value
    currentPage.value = page
    currentPageSize.value = pageSize
  }

  async function onPageChange(payload: {
    currentPage: number
    currentPageSize: number
    pageCount: number
    isFirstPage: boolean
    isLastPage: boolean
    prev: () => void
    next: () => void
  }) {
    if (disabledRef.value) {
      return
    }

    await wrappedFetchData(payload)

    if (typeof opts.onPageChange === "function") {
      opts.onPageChange(payload)
    }
  }

  async function onPageSizeChange(payload: {
    currentPage: number
    currentPageSize: number
    pageCount: number
    isFirstPage: boolean
    isLastPage: boolean
    prev: () => void
    next: () => void
  }) {
    await wrappedFetchData(payload)

    if (typeof opts.onPageSizeChange === "function") {
      opts.onPageSizeChange(payload)
    }
  }

  async function resetState(resetPage = true) {
    if (resetPage) {
      total.value = 0
      currentPage.value = 1
      return {
        currentPage: 1,
        currentPageSize: currentPageSize.value,
      }
    }

    return {
      currentPage: currentPage.value,
      currentPageSize: currentPageSize.value,
    }
  }

  // onBeforeMount(() => {
  //   if (!mutateRoute || !route.query.page) {
  //     return
  //   }

  //   const queryPage = Number(route.query.page)
  //   if (!Number.isNaN(queryPage) && queryPage !== currentPage.value) {
  //     currentPage.value = queryPage
  //   }
  // })

  // if (mutateRoute) {
  //   watch(currentPage, (v) => {
  //     currentPage.value = v
  //   }, { immediate: true })
  // }

  return {
    currentPage,
    currentPageSize,
    pageCount,
    handlePageChange,
    recoverPagination,
    onPageChange,
    onPageSizeChange,
    isFirstPage,
    isLastPage,
    prev,
    next,
    offset,
    resetState,
    disabled: disabledRef,
  }
}

import type { CategoryOption } from "../types"
import { getFetchHubProtocols } from "@/service/api/hub"
import { useClosableMessage, useLoading, usePagination } from "@airalogy/composables"

export function useHub() {
  const message = useClosableMessage()

  const searchQuery = ref("")
  const selectedCategory = ref<string>()
  const { loading: isLoading, startLoading, endLoading } = useLoading()
  const protocols = ref<Api.Hub.Protocol[]>([])
  const total = ref(0)

  const categoryOptions: CategoryOption[] = [
    { label: "All Categories", value: undefined, type: "category" },
    { label: "Biology", value: "biology", type: "category" },
    { label: "Chemistry", value: "chemistry", type: "category" },
    { label: "Physics", value: "physics", type: "category" },
  ]

  const pagination = usePagination({
    options: {
      page: 1,
      pageSize: 10,
      total,
    },
    fetchData: async ({ currentPage, currentPageSize }) => {
      await fetchProtocols(currentPage, currentPageSize)
    },
  })

  async function fetchProtocols(page: number, pageSize: number) {
    startLoading()
    try {
      const res = await getFetchHubProtocols({
        page,
        pageSize,
        name: searchQuery.value || undefined,
      })
      if (res) {
        protocols.value = res.protocols
        total.value = res.total_count
      }
    }
    catch (error) {
      message.error("Failed to fetch protocols")
    }
    finally {
      endLoading()
    }
  }

  watch([searchQuery, selectedCategory], () => {
    pagination.currentPage.value = 1
    pagination.handlePageChange(1)
  })

  return {
    // State
    searchQuery,
    selectedCategory,
    isLoading,
    protocols,
    total,
    // Options
    categoryOptions,
    // Methods
    fetchProtocols,
    // Pagination
    pagination,
  }
}

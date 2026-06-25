<template>
  <div class="max-w-full flex flex-1 flex-col">
    <slot name="header" />

    <n-spin :show="loading" content-class="min-h-90 flex flex-col" class="flex-1">
      <template v-if="!isEmpty">
        <slot :data="list" />
        <n-pagination
          class="mt-auto w-full justify-center pt-4"
          :page="currentPage"
          :page-size="currentPageSize"
          :page-count="pageCount"
          :page-sizes="props.pageSizes"
          :show-size-picker="props.showSizePicker"
          :disabled="disabled"
          @update:page="handlePageChange"
          @update:page-size="handlePageSizeChange"
        />
      </template>

      <slot v-else-if="loading" name="skeleton">
        <n-skeleton v-for="item in 5" :key="item" class="mb-3" :style="{ width: `${Math.min(Math.random(), 0.3) * 100 + 30}%` }" />
      </slot>
      <slot v-else-if="isEmpty" name="empty">
        <n-empty description="No data" />
      </slot>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import type { PaginationPayload } from "@airalogy/composables"
import { request } from "@/service/request"
import { useLoading, usePagination } from "@airalogy/composables"
import { nanoid } from "nanoid"

export interface FetchPayload extends PaginationPayload {
  requestId: string
}

// type FetchData = Api.GetResponseWithCount<string, any> | null
export type FetchData = { list: any[], total: number } | null

export interface Props {
  fetcher: (payload: FetchPayload) => Promise<FetchData>
  pageSize?: number
  pageSizes?: number[]
  showSizePicker?: boolean
  immediate?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  params: () => ({}),
  pageSize: 10,
  pageSizes: () => [10, 20, 50],
  showSizePicker: false,
  immediate: true,
})

const list = ref<any[]>([])
const total = ref<number>(0)
const isEmpty = computed(() => total.value === 0)
const { loading, startLoading, endLoading } = useLoading(true)

const pagination = usePagination<FetchData, FetchPayload>({
  options: { page: 1, pageSize: props.pageSize, total },
  fetchData: load,
})

const { currentPage, currentPageSize, handlePageChange, pageCount, resetState, disabled } = pagination

const requestId = ref<string>()

async function load(payload: FetchPayload) {
  startLoading()
  try {
    requestId.value = payload.requestId || nanoid()
    const data = await props.fetcher(payload)
    list.value = data?.list || []
    total.value = data?.total || 0

    return data
  }
  catch (error) {
    return null
  }
  finally {
    endLoading()
  }
}

async function reload(resetPage = true) {
  disabled.value = true
  const payload = await resetState(resetPage)

  try {
    return await load({ ...payload, requestId: nanoid() })
  }
  catch {
    // Handle error if needed
  }
  finally {
    disabled.value = false
  }
}

function handlePageSizeChange(pageSize: number) {
  currentPageSize.value = pageSize
}

watch(requestId, (_, prevId) => {
  if (prevId) {
    request.cancelRequest(prevId)
  }
})

watch(() => props.immediate, (val) => {
  if (val) {
    reload(false)
  }
}, { immediate: true })

defineExpose({
  load,
  reload,
  pagination,
})
</script>

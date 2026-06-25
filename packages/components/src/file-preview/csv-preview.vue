<template>
  <n-spin ref="wrapperRef" class="csv-preview-container" :show="isLoading" content-class="size-full">
    <n-card v-if="showPreviewCard" size="small" :bordered="false" content-class="size-full overflow-auto">
      <template #header>
        <slot name="header">
          <div class="w-full flex items-center justify-between">
            <div class="flex items-center gap-2">
              <n-icon size="16">
                <icon-ion-document-text-outline />
              </n-icon>
              <span class="text-sm font-medium">CSV Preview</span>

              <template v-if="isLimitedView">
                <n-tag size="small" type="info">
                  Limited View
                </n-tag>

                <div class="ml-2 text-xs text-gray-500">
                  Showing {{ displayDataLength }} of {{ totalRows }} rows,
                  {{ displayColumns }} of {{ totalCols }} columns
                </div>
              </template>
            </div>
            <div class="flex items-center gap-2">
              <slot name="header-actions" />
              <n-button
                v-if="showActions"
                size="small"
                quaternary
                @click="handleDownload"
              >
                <template #icon>
                  <n-icon><icon-ion-download-outline /></n-icon>
                </template>
                Download
              </n-button>
              <n-button
                v-if="showActions"
                size="small"
                quaternary
                @click="handleFullscreen"
              >
                <template #icon>
                  <n-icon><icon-ion-expand-outline /></n-icon>
                </template>
                Fullscreen
              </n-button>
            </div>
          </div>
        </slot>
      </template>

      <div v-if="isLoading" class="h-32 flex items-center justify-center">
        <n-spin size="small">
          <template #description>
            Loading CSV data...
          </template>
        </n-spin>
      </div>

      <div v-else-if="hasError" class="h-32 flex items-center justify-center text-red-500">
        <div class="text-center">
          <n-icon size="24" class="mb-2">
            <icon-ion-warning-outline />
          </n-icon>
          <div class="text-sm">
            {{ hasError }}
          </div>
        </div>
      </div>

      <div v-else-if="dataSource.length > 0" class="csv-table-container">
        <n-data-table
          ref="csvDataTable"
          :columns="tableColumns"
          :data="dataSource"
          :loading="isLoading"
          :virtual-scroll="useVirtualScroll"
          :virtual-scroll-x="useVirtualScroll"
          :virtual-scroll-header="useVirtualScroll"
          :flex-height="useVirtualScroll"
          :scroll-x="scrollX"
          :header-height="useVirtualScroll ? 56 : undefined"
          :min-row-height="useVirtualScroll ? 48 : undefined"
          :pagination="paginationConfig"
          :bordered="true"
          size="small"
          class="csv-data-table"
          v-bind="$attrs"
        />
      </div>

      <div v-else-if="!isLoading && !hasError" class="h-32 flex items-center justify-center text-gray-500">
        <div class="text-center">
          <n-icon size="24" class="mb-2">
            <icon-ion-document-text-outline />
          </n-icon>
          <div class="text-sm">
            No data to preview
          </div>
        </div>
      </div>
    </n-card>

    <template v-else>
      <n-data-table
        v-if="dataSource.length > 0"
        ref="csvDataTable"
        :columns="tableColumns"
        :data="dataSource"
        :loading="isLoading"
        :virtual-scroll="useVirtualScroll"
        :virtual-scroll-x="useVirtualScroll"
        :virtual-scroll-header="useVirtualScroll"
        :flex-height="useVirtualScroll"
        table-layout="auto"
        :scroll-x="scrollX"
        :header-height="useVirtualScroll ? 56 : undefined"
        :min-row-height="useVirtualScroll ? 48 : undefined"
        :pagination="paginationConfig"
        :bordered="true"
        size="small"
        class="size-full"
        v-bind="$attrs"
      />

      <div v-else class="h-32 flex items-center justify-center text-gray-500">
        <div class="text-center">
          <n-icon size="24" class="mb-2">
            <icon-ion-document-text-outline />
          </n-icon>
          <div class="text-sm">
            No data to preview
          </div>
        </div>
      </div>
    </template>
  </n-spin>
</template>

<script setup lang="ts">
import type { Options } from "csv-parse/browser/esm"
import type { DataTableColumns, DataTableInst, PaginationProps } from "naive-ui"
import { useBoolean, useClosableMessage } from "@airalogy/composables"
// import { fetchCsvContent } from "@airalogy/service/api/common"
import { downloadAs } from "@airalogy/shared/utils"
import { unrefElement } from "@vueuse/core"
import IconIonDocumentTextOutline from "~icons/ion/document-text-outline"
import IconIonDownloadOutline from "~icons/ion/download-outline"
import IconIonExpandOutline from "~icons/ion/expand-outline"
import IconIonWarningOutline from "~icons/ion/warning-outline"
import { parse as csvParse } from "csv-parse/browser/esm/sync"
import { NButton, NCard, NDataTable, NIcon, NSpin, NTag } from "naive-ui"
import { computed, onMounted, ref, toRefs, watch } from "vue"

interface IProps {
  fileUrl?: string
  file?: File | null
  content?: string | null
  maxRows?: number
  maxCols?: number
  options?: Options
  showCard?: boolean
  showActions?: boolean
  pageSize?: number
  showSizePicker?: boolean
  pageSizes?: number[]
}

const props = withDefaults(defineProps<IProps>(), {
  fileUrl: "",
  file: null,
  content: null,
  maxRows: Infinity,
  maxCols: Infinity,
  options: () => ({
    columns: true,
    skip_empty_lines: true,
  }),
  showCard: true,
  showActions: false,
  pageSize: 5,
  showSizePicker: true,
  pageSizes: () => [5, 10, 20, 50, 100],
})

const emit = defineEmits<{
  (e: "error", value: string): void
  (e: "load", url: string): Promise<string>
}>()

const { bool: isLoading, setTrue: startLoading, setFalse: endLoading } = useBoolean()
const hasError = ref<string>("")
const dataSource = ref<any[]>([])
const tableColumns = ref<DataTableColumns<any>>([])
const totalRows = ref(0)
const totalCols = ref(0)
const scrollX = ref(0)
const csvDataTable = ref<DataTableInst | null>(null)

// Pagination state
const currentPage = ref(1)
const currentPageSize = ref(props.pageSize)

const { file, options, content, fileUrl } = toRefs(props)
const message = useClosableMessage()

// Computed properties
const showPreviewCard = computed(() => props.showCard)
const useVirtualScroll = computed(() => props.maxRows === Infinity && props.maxCols === Infinity)
const isLimitedView = computed(() => {
  if (props.maxRows === Infinity || props.maxCols === Infinity) {
    return true
  }

  return totalRows.value > props.maxRows || totalCols.value > props.maxCols
})

const displayDataLength = computed((): number => {
  // Virtual scroll mode - return all data
  if (useVirtualScroll.value) {
    return dataSource.value.length
  }

  // Pagination mode - slice data based on current page
  const startIndex = (currentPage.value - 1) * currentPageSize.value
  const endIndex = startIndex + currentPageSize.value
  return endIndex - startIndex
})

const displayColumns = computed(() => {
  if (tableColumns.value.length === 0)
    return 0
  return Math.min(props.maxCols, totalCols.value)
})

// Pagination event handlers
function handleUpdatePage(page: number) {
  currentPage.value = page
}

function handleUpdatePageSize(pageSize: number) {
  currentPageSize.value = pageSize
  currentPage.value = 1 // Reset to first page when page size changes
}

// Pagination configuration
const paginationConfig = computed(() => {
  // No pagination when using virtual scroll
  if (useVirtualScroll.value) {
    return false
  }

  // No pagination when no data
  if (dataSource.value.length === 0) {
    return false
  }

  // Return proper pagination configuration
  return {
    page: currentPage.value,
    pageSize: currentPageSize.value,
    itemCount: totalRows.value,
    showSizePicker: props.showSizePicker,
    pageSizes: props.pageSizes,
    onUpdatePage: handleUpdatePage,
    onUpdatePageSize: handleUpdatePageSize,
    prefix: ({ itemCount }) => `Total: ${itemCount} rows`,
  } satisfies PaginationProps
})

// Generate columns for the data table
function generateColumns(records: Record<string, any>[]): DataTableColumns<any> {
  if (!records[0])
    return []

  const allKeys = Object.keys(records[0])
  const keysToShow = props.maxCols === Infinity
    ? allKeys
    : allKeys.slice(0, props.maxCols)

  const columns: DataTableColumns<any> = keysToShow.map((key, idx) => ({
    title: key,
    key,
    resizable: true,
    // width: useVirtualScroll.value ? 100 : 120,
    minWidth: 100,
    maxWidth: 500,
    // ellipsis: true,
    // render: useVirtualScroll.value
    //   ? undefined
    //   : (row: any) => {
    //       const value = row[key]
    //       return value !== undefined ? String(value) : ""
    //     },
  }))

  // Add row number column for preview mode
  if (!useVirtualScroll.value) {
    columns.unshift({
      key: "_rowIndex",
      title: "#",
      width: 70,
      align: "center",
      fixed: "left",
      render: (row: any, index: number) => index + 1 + (currentPage.value - 1) * currentPageSize.value,
    })
  }

  return columns
}

// Load and parse CSV data
async function loadCsvData() {
  const fileUrlVal = toValue(fileUrl)
  const fileVal = toValue(file)
  const contentVal = toValue(content)
  if (!fileUrlVal && !fileVal && !contentVal) {
    return
  }

  // Add setImmediate polyfill for csv-parse
  if (!window.setImmediate) {
    // eslint-disable-next-line ts/ban-ts-comment
    // @ts-expect-error
    window.setImmediate = (fn: (arg: any[]) => any) => setTimeout(fn, 0)
  }

  startLoading()
  hasError.value = ""

  try {
    let csvContent: string

    // Handle different data sources
    if (contentVal) {
      csvContent = contentVal
    }
    else if (fileVal) {
      csvContent = await fileVal.text()
    }
    else if (fileUrlVal) {
      csvContent = await emit("load", fileUrlVal)
    }
    else {
      return
    }

    // Parse CSV using csv-parse library
    const records = csvParse(csvContent, options.value) as unknown as Record<string, any>[]

    if (records.length === 0) {
      dataSource.value = []
      tableColumns.value = []
      totalRows.value = 0
      totalCols.value = 0
      return
    }

    // Set data
    dataSource.value = records
    totalRows.value = records.length
    totalCols.value = Object.keys(records[0]).length

    // Generate columns
    tableColumns.value = generateColumns(records)
    scrollX.value = tableColumns.value.length * 100
  }
  catch (err) {
    const errorMessage = err instanceof Error ? err.message : "Failed to load CSV data"
    hasError.value = errorMessage
    message.error(errorMessage)
    console.error("CSV loading error:", err)
    emit("error", errorMessage)
  }
  finally {
    endLoading()
  }
}

// Watch for changes in props
watch(() => [props.fileUrl, props.file, props.content, options.value], () => {
  // Reset pagination when data source changes
  currentPage.value = 1
  loadCsvData()
}, { immediate: false })

// Watch for pageSize prop changes
watch(() => props.pageSize, (newPageSize) => {
  currentPageSize.value = newPageSize
  currentPage.value = 1
})

// Action handlers
function handleDownload() {
  try {
    if (!props.file && !props.content && !props.fileUrl) {
      message.error("No data available for download")
      return
    }

    let csvContent: string = ""
    let filename: string = "data.csv"

    if (props.content) {
      csvContent = props.content
    }
    else if (props.file) {
      filename = props.file.name
      // For file objects, we need to convert back to CSV format
      csvContent = convertDataToCsv()
    }
    else if (props.fileUrl) {
      filename = props.fileUrl.split("/").pop() || "data.csv"
      csvContent = convertDataToCsv()
    }

    downloadAs(csvContent, filename, "text/csv;charset=utf-8;")
    message.success("CSV file downloaded successfully")
  }
  catch (error) {
    const errorMessage = error instanceof Error ? error.message : "Failed to download CSV"
    message.error(errorMessage)
    console.error("Download error:", error)
  }
}

function convertDataToCsv(): string {
  if (dataSource.value.length === 0)
    return ""

  const headers = Object.keys(dataSource.value[0]).filter(key => key !== "_rowIndex")
  const csvRows = [
    headers.join(","),
    ...dataSource.value.map(row =>
      headers.map((header) => {
        const value = row[header]
        // Escape commas and quotes in CSV values
        if (typeof value === "string" && (value.includes(",") || value.includes("\"") || value.includes("\n"))) {
          return `"${value.replace(/"/g, "\"\"")}"`
        }
        return value
      }).join(","),
    ),
  ]

  return csvRows.join("\n")
}

function handleFullscreen() {
  try {
    // Use native browser fullscreen API on the document
    if (document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen().then(() => {
        message.success("Entered fullscreen mode")
      }).catch(() => {
        message.info("Fullscreen mode not supported or blocked")
      })
    }
    else {
      message.info("Fullscreen API not supported in this browser")
    }
  }
  catch (error) {
    const errorMessage = error instanceof Error ? error.message : "Failed to enter fullscreen"
    message.error(errorMessage)
    console.error("Fullscreen error:", error)
  }
}

const wrapperRef = ref<HTMLElement | null>(null)
watch(currentPageSize, () => {
  const el = unrefElement(wrapperRef)
  if (!el) {
    return
  }

  el.style.setProperty("height", null)
})

onMounted(() => {
  loadCsvData()
})
</script>

<style scoped lang="sass">
:deep(.n-pagination)
  @apply items-center max-w-full flex-wrap
:deep(.n-pagination-prefix)
  @apply whitespace-nowrap

:deep(.n-data-table-base-table)
  @apply size-full
</style>

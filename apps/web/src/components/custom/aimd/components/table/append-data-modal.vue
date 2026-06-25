<template>
  <n-modal
    v-model:show="showModal"
    class="max-h-4xl max-w-6xl"
    preset="card"
    title="Insert Table Data"
    :closable="false"
    :mask-closable="false"
  >
    <div class="flex flex-col gap-4">
      <!-- Mode Selection -->
      <div class="flex items-center gap-4">
        <n-radio-group v-model:value="mode" class="flex-1">
          <n-radio value="append">
            Append to existing data
          </n-radio>
          <n-radio value="replace">
            Replace all existing data
          </n-radio>
        </n-radio-group>

        <n-button @click="handleClearGrid">
          <template #icon>
            <icon-tabler-eraser />
          </template>
          Clear Grid
        </n-button>

        <n-button @click="handlePasteFromClipboard">
          <template #icon>
            <icon-paste />
          </template>
          Paste
        </n-button>
      </div>

      <!-- Column Headers -->
      <div v-if="columns.length > 0" class="overflow-hidden border border-gray-200 rounded-lg">
        <div class="grid border-b bg-gray-50" :style="{ gridTemplateColumns: gridTemplate }">
          <div class="border-r px-3 py-2 text-xs text-gray-500 font-medium">
            Row
          </div>
          <div
            v-for="column in columns"
            :key="column.key"
            class="border-r px-3 py-2 text-xs text-gray-900 font-medium last:border-r-0"
          >
            <div class="flex items-center gap-1">
              <span class="truncate">{{ column.title }}</span>
              <n-tooltip v-if="column.description" trigger="hover">
                <template #trigger>
                  <icon-information class="text-gray-400" />
                </template>
                {{ column.description }}
              </n-tooltip>
              <span
                v-if="column.required"
                class="text-xs text-red-500"
                title="Required field"
              >*</span>
            </div>
            <div class="mt-1 text-xs text-gray-500">
              {{ column.type }}
            </div>
          </div>
        </div>

        <!-- Data Grid -->
        <div class="max-h-96 overflow-auto">
          <div
            v-for="(row, rowIndex) in gridData"
            :key="rowIndex"
            class="grid border-b hover:bg-gray-50"
            :style="{ gridTemplateColumns: gridTemplate }"
          >
            <!-- Row Number -->
            <div class="flex items-center border-r bg-gray-50 px-3 py-2 text-sm text-gray-500">
              {{ rowIndex + 1 }}
              <n-button
                text
                size="tiny"
                class="ml-2"
                @click="handleRemoveRow(rowIndex)"
              >
                <template #icon>
                  <icon-delete class="text-red-500" />
                </template>
              </n-button>
            </div>

            <!-- Data Cells -->
            <div
              v-for="column in columns"
              :key="column.key"
              class="relative border-r last:border-r-0"
            >
              <component
                :is="getCellComponent(column.type)"
                v-model:value="row[column.key]"
                :placeholder="column.title"
                :type="column.type"
                :required="column.required"
                :options="column.options"
                class="w-full border-0 px-3 py-2 text-sm focus:outline-none focus:ring-0" :class="[
                  getCellValidationClass(row[column.key], column),
                ]"
                @blur="handleCellBlur(rowIndex, column.key, $event)"
                @focus="handleCellFocus(rowIndex, column.key)"
              />

              <!-- Validation Error Indicator -->
              <div
                v-if="getCellError(row[column.key], column)"
                class="absolute right-0 top-0 h-0 w-0 border-l-8 border-t-8 border-l-transparent border-t-red-500"
                :title="getCellError(row[column.key], column)"
              />
            </div>
          </div>
        </div>

        <!-- Add Row Button -->
        <div class="border-t bg-gray-50 p-3">
          <n-button size="small" @click="handleAddRow">
            <template #icon>
              <icon-add />
            </template>
            Add Row
          </n-button>
        </div>
      </div>

      <!-- Import Options -->
      <n-collapse>
        <n-collapse-item title="Import Options" name="import">
          <div class="space-y-4">
            <div>
              <label class="mb-2 block text-sm font-medium">Import from Text</label>
              <n-input
                v-model:value="importText"
                type="textarea"
                placeholder="Paste tab-separated or comma-separated data here..."
                :rows="4"
                @blur="handleParseImportText"
              />
            </div>

            <div class="flex items-center gap-2">
              <n-checkbox v-model:checked="hasHeader">
                First row contains headers
              </n-checkbox>
              <n-select
                v-model:value="separator"
                :options="separatorOptions"
                class="w-32"
                placeholder="Separator"
              />
            </div>
          </div>
        </n-collapse-item>
      </n-collapse>

      <!-- Summary -->
      <div v-if="gridData.length > 0" class="rounded-lg bg-blue-50 p-3">
        <div class="flex items-center gap-4 text-sm">
          <span class="font-medium">Summary:</span>
          <span>{{ gridData.length }} row(s)</span>
          <span>{{ validRowCount }} valid</span>
          <span v-if="errorCount > 0" class="text-red-600">
            {{ errorCount }} error(s)
          </span>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-between">
        <div class="flex gap-2">
          <n-button @click="handleCancel">
            Cancel
          </n-button>
        </div>
        <div class="flex gap-2">
          <n-button :disabled="gridData.length === 0" @click="handlePreview">
            Preview Changes
          </n-button>
          <n-button
            type="primary"
            :disabled="gridData.length === 0 || errorCount > 0"
            :loading="isProcessing"
            @click="handleConfirm"
          >
            {{ mode === 'append' ? 'Append Data' : 'Replace Data' }}
          </n-button>
        </div>
      </div>
    </template>
  </n-modal>

  <!-- Preview Modal -->
  <n-modal
    v-model:show="showPreview"
    class="max-w-4xl"
    preset="card"
    title="Preview Changes"
  >
    <div class="space-y-4">
      <div class="text-sm text-gray-600">
        <strong>Mode:</strong> {{ mode === 'append' ? 'Append' : 'Replace' }}
        ({{ gridData.length }} row(s))
      </div>

      <n-data-table
        :columns="previewColumns"
        :data="gridData"
        :pagination="{ pageSize: 10 }"
        size="small"
        :bordered="true"
      />
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="showPreview = false">
          Close
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="tsx">
import type { DataTableColumns } from "naive-ui"
import { getSubvarNames } from "@airalogy/aimd-core"
import { formatDate } from "@airalogy/shared/utils"
import IconPaste from "~icons/tabler/clipboard-text"
import IconInformation from "~icons/tabler/info-circle"
import IconAdd from "~icons/tabler/plus"
import IconDelete from "~icons/tabler/trash"
import { NButton, NCheckbox, NDatePicker, NInput, NInputNumber, NSelect, NSwitch, useMessage } from "naive-ui"
import { computed, h, ref, watch } from "vue"
import { getInputType } from "../../composables/useAIMDHelpers"

// Import TableInfo from batch-table-processor for type consistency
import type { TableInfo } from "./batch-table-processor"

interface ColumnInfo {
  key: string
  title: string
  description?: string
  type: string
  pattern?: string
  required: boolean
  options?: { label: string, value: any }[]
}

interface Props {
  show: boolean
  info: TableInfo
  tableRecord: Record<string, Record<string, any>>
  onConfirm: (data: any[], mode: "append" | "replace") => Promise<void>
}

const props = defineProps<Props>()
const emit = defineEmits<{
  "update:show": [value: boolean]
}>()

const message = useMessage()

// Reactive state
const showModal = computed({
  get: () => props.show,
  set: value => emit("update:show", value),
})

const mode = ref<"append" | "replace">("append")
const gridData = ref<Record<string, any>[]>([])
const importText = ref("")
const hasHeader = ref(true)
const separator = ref("tab")
const isProcessing = ref(false)
const showPreview = ref(false)

// Configuration
const separatorOptions = [
  { label: "Tab", value: "tab" },
  { label: "Comma", value: "comma" },
  { label: "Semicolon", value: "semicolon" },
  { label: "Pipe", value: "pipe" },
]

const separatorMap = {
  tab: "\t",
  comma: ",",
  semicolon: ";",
  pipe: "|",
}

// Computed properties
const columns = computed<ColumnInfo[]>(() => {
  if (!props.info?.subvars || !props.tableRecord) {
    return []
  }

  const { name: tableName, subvars } = props.info
  const tableInfo = props.tableRecord[tableName] || {}

  // Normalize subvars to string[] using getSubvarNames
  const subvarNames = getSubvarNames(subvars)

  return subvarNames.map((subvar) => {
    const fieldInfo = tableInfo[subvar] || {}
    const inputType = getInputType(fieldInfo)

    return {
      key: subvar,
      title: fieldInfo.title || subvar,
      description: fieldInfo.description,
      type: inputType,
      pattern: fieldInfo.pattern,
      required: fieldInfo.required || false,
      options: fieldInfo.enum
        ? Object.entries(fieldInfo.enum).map(([key, value]) => ({
          label: String(value),
          value: key,
        }))
        : undefined,
    }
  })
})

const gridTemplate = computed(() => {
  const columnCount = columns.value.length
  return `60px repeat(${columnCount}, 1fr)`
})

const validRowCount = computed(() => {
  return gridData.value.filter(row =>
    columns.value.every(col => !getCellError(row[col.key], col)),
  ).length
})

const errorCount = computed(() => {
  return gridData.value.reduce((count, row) => {
    const rowErrors = columns.value.filter(col => getCellError(row[col.key], col))
    return count + rowErrors.length
  }, 0)
})

const previewColumns = computed<DataTableColumns>(() => {
  return columns.value.map(col => ({
    key: col.key,
    title: col.title,
    width: 150,
    render: (row: any) => {
      const value = row[col.key]
      const error = getCellError(value, col)

      return h("div", {
        class: error ? "text-red-600" : "",
      }, [
        formatCellValue(value, col.type),
        error && h("div", {
          class: "text-xs text-red-500 mt-1",
        }, error),
      ])
    },
  }))
})

// Component selection for different cell types
function getCellComponent(type: string) {
  switch (type) {
    case "integer":
    case "float":
    case "number":
      return NInputNumber
    case "boolean":
      return NSwitch
    case "date":
    case "datetime":
      return NDatePicker
    case "enum":
    case "select":
      return NSelect
    default:
      return NInput
  }
}

// Cell validation
function getCellError(value: any, column: ColumnInfo): string {
  // Required field validation
  if (column.required && (value === null || value === undefined || value === "")) {
    return `${column.title} is required`
  }

  // Type validation
  if (value !== null && value !== undefined && value !== "") {
    switch (column.type) {
      case "integer":
        if (!Number.isInteger(Number(value))) {
          return "Must be a whole number"
        }
        break
      case "float":
      case "number":
        if (Number.isNaN(Number(value))) {
          return "Must be a valid number"
        }
        break
      case "boolean":
        if (typeof value !== "boolean" && value !== "true" && value !== "false") {
          return "Must be true or false"
        }
        break
      case "date":
      case "datetime":
        if (Number.isNaN(Date.parse(value))) {
          return "Must be a valid date"
        }
        break
    }

    // Pattern (regex) validation
    if (column.pattern) {
      const stringVal = String(value).trim()
      if (stringVal) {
        try {
          const regex = new RegExp(column.pattern)
          if (!regex.test(stringVal)) {
            return "Invalid format: does not match required pattern"
          }
        }
        catch (e) {
          console.warn("Invalid regex pattern:", column.pattern, e)
        }
      }
    }
  }

  return ""
}

function getCellValidationClass(value: any, column: ColumnInfo): string {
  const error = getCellError(value, column)
  return error ? "border-red-300 bg-red-50" : "border-gray-200"
}

// Data conversion utilities
function convertCellValue(value: any, type: string): any {
  if (value === null || value === undefined || value === "") {
    return null
  }

  switch (type) {
    case "integer":
      return Number.parseInt(String(value), 10)
    case "float":
    case "number":
      return Number.parseFloat(String(value))
    case "boolean":
    {
      if (typeof value === "boolean")
        return value
      const strValue = String(value).toLowerCase()
      return strValue === "true" || strValue === "1" || strValue === "yes"
    }
    case "date":
    case "datetime":
      return new Date(value).toISOString()
    default:
      return String(value)
  }
}

function formatCellValue(value: any, type: string): string {
  if (value === null || value === undefined)
    return ""

  switch (type) {
    case "boolean":
      return value ? "Yes" : "No"
    case "date":
      return formatDate(value, "date-short")
    case "datetime":
      return formatDate(value, "date-time")
    default:
      return String(value)
  }
}

// Event handlers
function handleAddRow() {
  const newRow: Record<string, any> = {}
  columns.value.forEach((col) => {
    newRow[col.key] = null
  })
  gridData.value.push(newRow)
}

function handleRemoveRow(index: number) {
  gridData.value.splice(index, 1)
}

function handleClearGrid() {
  gridData.value = []
}

async function handlePasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText()
    if (text) {
      importText.value = text
      handleParseImportText()
    }
  }
  catch (err) {
    message.error("Failed to read clipboard. Please paste manually in the import text area.")
  }
}

function handleParseImportText() {
  if (!importText.value.trim())
    return

  const sep = separatorMap[separator.value as keyof typeof separatorMap]
  const lines = importText.value.trim().split("\n")

  if (lines.length === 0)
    return

  let dataLines = lines
  let headers: string[] = []

  if (hasHeader.value && lines.length > 0) {
    headers = lines[0].split(sep).map(h => h.trim())
    dataLines = lines.slice(1)
  }

  const parsedData = dataLines.map((line) => {
    const values = line.split(sep).map(v => v.trim())
    const row: Record<string, any> = {}

    columns.value.forEach((col, index) => {
      const value = values[index] || null
      row[col.key] = convertCellValue(value, col.type)
    })

    return row
  })

  gridData.value = parsedData
  importText.value = ""
  message.success(`Imported ${parsedData.length} rows`)
}

function handleCellFocus(rowIndex: number, columnKey: string) {
  // Could add cell focus highlighting here
}

function handleCellBlur(rowIndex: number, columnKey: string, event: any) {
  const value = event.target?.value
  const column = columns.value.find(col => col.key === columnKey)

  if (column) {
    gridData.value[rowIndex][columnKey] = convertCellValue(value, column.type)
  }
}

function handlePreview() {
  showPreview.value = true
}

function handleCancel() {
  showModal.value = false
  gridData.value = []
  importText.value = ""
}

async function handleConfirm() {
  if (errorCount.value > 0) {
    message.error("Please fix all validation errors before proceeding")
    return
  }

  isProcessing.value = true

  try {
    // Convert data to the format expected by handleSetTableVariableRecord
    const processedData = gridData.value.map((row) => {
      const processedRow: Record<string, any> = {}
      columns.value.forEach((col) => {
        processedRow[col.key] = convertCellValue(row[col.key], col.type)
      })
      return processedRow
    })

    await props.onConfirm(processedData, mode.value)

    message.success(`Successfully ${mode.value === "append" ? "appended" : "replaced"} ${processedData.length} rows`)
    showModal.value = false
    gridData.value = []
  }
  catch (error) {
    message.error(`Failed to ${mode.value} data: ${error instanceof Error ? error.message : "Unknown error"}`)
  }
  finally {
    isProcessing.value = false
  }
}

// Initialize with empty row when modal opens
watch(() => props.show, (show) => {
  if (show && gridData.value.length === 0) {
    handleAddRow()
  }
})

// Auto-add row when typing in the last row
watch(gridData, (newData) => {
  if (newData.length > 0) {
    const lastRow = newData[newData.length - 1]
    const hasData = columns.value.some(col =>
      lastRow[col.key] !== null && lastRow[col.key] !== undefined && lastRow[col.key] !== "",
    )

    if (hasData) {
      // Add a new empty row
      handleAddRow()
    }
  }
}, { deep: true })
</script>

<style scoped lang="sass">
:deep(.n-input__input),
:deep(.n-input-number__input),
:deep(.n-date-picker__input)
  border: none !important
  box-shadow: none !important

:deep(.n-switch)
  margin: 8px

.grid
  display: grid
</style>

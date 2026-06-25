<template>
  <n-form-item
    :ref="(el: any) => handleFormItemRef(`${props.scope}_${props.info.name}`, el)"
    :path="`${props.scope}.${props.info.name}.value`"
    :show-label="false"
    class="var-table-form-item w-full text-start"
    :show-require-mark="false"
  >
    <div class="w-full text-left">
      <div class="aimd-field aimd-field--no-style aimd-field__label cursor-pointer" @paste="onPaste">
        <insert-wbr text="table" class="aimd-field__scope aimd-field__scope--var_table" />
        <insert-wbr :text="props.info.name" class="aimd-field__name flex-1" />
      </div>
      <n-data-table
        :columns="columns" :data="data" :bordered="true" :single-line="false" class="!mb-0"
        :style="{ '--n-empty-padding': '0px' }"
      >
        <template #empty>
          <div />
        </template>
      </n-data-table>
      <n-button
        v-if="showAddButton"
        dashed
        :disabled="disabled"
        class="mt-2"
        @click="handleAddVarTableRow(info)"
      >
        <template #icon>
          <icon-add-circle />
        </template>
        Add Row
      </n-button>
    </div>
  </n-form-item>

  <!-- Enhanced Append Data Modal -->
  <append-data-modal
    v-model:show="showAppendModal"
    :info="info"
    :table-record="tableVariableRecord"
    :on-confirm="handleBatchDataUpdate"
  />
</template>

<script setup lang="tsx">
import type { DataTableColumns } from "naive-ui"
import InsertWbr from "@/components/common/insert-wbr.vue"
import { getSubvarNames } from "@airalogy/aimd-core"
import IconInformation from "~icons/tabler/info-circle"
import IconAddCircle from "~icons/tabler/plus"
import IconDelete from "~icons/tabler/trash"
import { isEmpty } from "lodash-es"
import { NButton, NFormItem, NIcon, NTooltip, useMessage } from "naive-ui"
import { computed, h, onMounted, ref } from "vue"
import { useAIMDInject } from "../../composables/useAIMDHelpers"
import AIMDItem from "../aimd-item.vue"
import AppendDataModal from "./append-data-modal.vue"
import { createBatchTableProcessor, type TableInfo } from "./batch-table-processor"

interface Props {
  info: TableInfo
  model: any
  scope?: string
  disabled?: boolean
  type?: string
}

const props = withDefaults(defineProps<Props>(), {
  type: "var-table-header",
})

const { tableVariableRecord, handleRemoveVarTableRow, handleAddVarTableRow, handleSetTableVariableRecord, readonly: isReadonly, handleGetTableHeader, fieldModel, handleFormItemRef } = useAIMDInject()!
const message = useMessage()
const showAppendModal = ref(false)

const data = computed(() => {
  return tableVariableRecord.value[props.info.name] as any[]
})

// Use unified utility to normalize subvars to string array
const subvarNames = computed<string[]>(() => getSubvarNames(props.info.subvars))

const showAddButton = computed(() => {
  return !isReadonly.value && (props.info.link ? props.info.link.isSource : subvarNames.value.length > 0)
})

const columns = computed<DataTableColumns>(() => {
  const subvars = subvarNames.value
  const width = subvars.length ? `calc(100% / ${subvars.length})` : undefined
  const varColumns = subvars.map((rvName: string) => ({
    key: rvName,
    resizable: true,
    width,
    title: () => {
      const header = handleGetTableHeader(props.info.name, rvName)
      if (!header) {
        return rvName
      }

      const { title, description } = header

      return (
        <div class="w-full flex items-center gap-1">
          <span class="break-words font-medium">{title || rvName}</span>
          {description
            ? (
                <NTooltip trigger="hover" placement="top">
                  {{
                    trigger: () => (
                      <NIcon class="cursor-help text-gray-400 hover:text-primary">
                        {{
                          default: () => h(IconInformation),
                        }}
                      </NIcon>
                    ),
                    default: () => description,
                  }}
                </NTooltip>
              )
            : null}
        </div>
      )
    },
    render: (row: any) => {
      if (!row[rvName]) {
        return h("span", { class: "text-error" }, "ERROR")
      }
      return h(AIMDItem, {
        ...row[rvName],
        class: "min-w-fit",
      })
    },
  }))

  if (isReadonly.value || !(props.info.link ? props.info.link.isSource : true)) {
    return varColumns
  }

  return [
    {
      key: "row",
      width: 50,
      title: "Row",
      className: "whitespace-nowrap",
      fixed: "left",
      render: (row: any, index: number) => {
        return (
          <div class="flex items-center gap-1">
            <span class="ml-2">{index + 1}</span>
            <NButton quaternary class="h-6 w-6 text-gray-400 !p-0 hover:text-error" onClick={() => handleRemoveVarTableRow(props.info.name, index)}>
              {{
                icon: () => (
                  <NIcon size={12}>
                    <IconDelete />
                  </NIcon>
                ),
              }}
            </NButton>
          </div>
        )
      },
    },
    ...varColumns,
  ]
})

onMounted(() => {
  const { info, model } = props
  if (isEmpty(info) || !Array.isArray(model) || model.length === 0) {
    return
  }

  model.forEach((_, index) => {
    handleSetTableVariableRecord(info, model, index)
  })
})

/**
 * Enhanced batch data update handler using the new batch processor
 */
async function handleBatchDataUpdate(data: Record<string, any>[], mode: "append" | "replace"): Promise<void> {
  try {
    // Create batch processor instance
    const processor = createBatchTableProcessor(props.info, tableVariableRecord.value)

    // Create batch operation
    const batchOperation = processor.createBatchOperation(
      handleSetTableVariableRecord,
      fieldModel,
      tableVariableRecord,
    )

    // Execute the batch operation
    const result = await batchOperation(data, mode)

    if (result.success) {
      message.success(`Successfully ${mode === "append" ? "appended" : "replaced"} ${result.processedRows} rows`)
    }
    else {
      throw new Error("Batch operation failed")
    }
  }
  catch (error) {
    console.error("Batch update error:", error)
    throw error // Re-throw for the modal to handle
  }
}

/**
 * Enhanced paste handler that opens the append modal with parsed data
 */
function onPaste(e: ClipboardEvent) {
  if (isReadonly.value || props.disabled)
    return

  const clipboardData = e.clipboardData || (window as any).clipboardData
  if (!clipboardData)
    return

  const text = clipboardData.getData("text")
  if (!text)
    return

  // Open the append modal for better data handling
  showAppendModal.value = true

  // The modal will handle the clipboard data internally
  e.preventDefault()
}
</script>

<style scoped lang="sass">
:deep(.n-input-wrapper)
  padding: 6px 10px

:deep(.n-data-table)
  .n-data-table-td
    padding: 8px
  .n-data-table-tr:hover .opacity-0
    opacity: 1
:deep(.n-data-table-table)
  margin-bottom: 0!important

// Fix border-radius for table cell inputs (override the bottom-only radius from aimd-input)
:deep(.checkbox__wrapper)
  border-radius: 6px !important

// Override naive-ui input border-radius for table cells
:deep(.n-input)
  --n-border-radius: 6px !important
  border-radius: 6px !important

:deep(.n-input-number)
  --n-border-radius: 6px !important
  border-radius: 6px !important

:deep(.n-input-wrapper)
  border-radius: 6px !important

:deep(.n-input__border)
  border-radius: 6px !important

:deep(.n-input__state-border)
  border-radius: 6px !important
</style>

<template>
  <main class="relative min-h-40">
    <n-data-table
      class="mt-6"
      :columns="columns"
      :data="parsed"
      :bordered="false"
      :pagination="{ page: currentPage, pageCount, pageSize: currentPageSize }"
      @update:page="handlePageChange"
    />
  </main>
</template>

<script setup lang="ts">
import type { IFieldItem } from "@/views/project-protocols/modules/protocol/types/types"
import type { FieldKey } from "@airalogy/shared"
import type { ProtocolModels } from "@airalogy/shared/types"
import { usePagination } from "@/composables"
import { $t } from "@airalogy/shared/locales"
import { type DataTableColumns, NTag } from "naive-ui"
import { useProtocolInfoStore } from "../../hooks/useProtocolInfoStore"

// type FieldRecord = Record<string, IFieldItem & { format?: string }>
interface Props {
  item: ProtocolModels.ProjectProtocolInfo
}
const props = defineProps<Props>()

const { protocolInfo } = useProtocolInfoStore()!

const typeMap = {
  string: "primary",
  number: "success",
  boolean: "info",
  method: "default",
  regexp: "default",
  integer: "warning",
  float: "warning",
  array: "default",
  object: "default",
  // 其他情况...
  default: "default",
}
const columns = ref<DataTableColumns<Api.ResearchNode.ResearchNodeField>>([
  { title: $t("common.id"), key: "label" },
  { title: $t("common.title"), key: "title" },
  {
    title: $t("common.type"),
    key: "type",
    render(row) {
      const { type } = row
      return type
        ? h(
          NTag,
          {
            type: typeMap[type] as any,
            bordered: false,
          },
          {
            default: () => type as string,
          },
        )
        : ""
    },
  },
  {
    title: $t("common.format"),
    key: "format",
    render(row) {
      const { format } = row as any
      return format
        ? h(
          NTag,
          {
            type: typeMap[format as keyof typeof typeMap] as any,
            bordered: false,
          },
          {
            default: () => format as string,
          },
        )
        : ""
    },
  },
])

const parsed = computed(() => {
  if (!protocolInfo.value) {
    return []
  }

  const fields = protocolInfo.value.fields as ProtocolModels.Fields
  const jsonSchema = protocolInfo.value.json_schema as ProtocolModels.JsonSchema

  if (!fields || !jsonSchema)
    return []

  const data: (IFieldItem & { format: string })[] = []

  Object.entries(fields).forEach(([k, v]) => {
    const schema = jsonSchema[k as keyof ProtocolModels.JsonSchema]
    const { properties, required, title: scopeTitle, type: scopeType } = schema || {}
    const hasRequired = Boolean(required)

    v.forEach((it) => {
      const { name } = it
      const isRequired = Boolean(
        hasRequired && required && required.findIndex(prop => prop === name) !== -1,
      )
      const { title, type, format } = (properties?.[name] as any) || {}

      data.push({
        label: name,
        disabled: false,
        value: undefined,
        scope: k as FieldKey,
        title,
        type,
        format,
        required: isRequired,
        id: `scope-${k}-${name}`,
      })
    })
  })

  return data
})

const { currentPage, currentPageSize, pageCount, handlePageChange } = usePagination({
  options: { total: parsed.value.length, page: 1, pageSize: 10 },
})
</script>

<style scoped lang="sass">
:deep(.n-data-table__pagination)
  margin-top: 4rem
  justify-content: center
</style>

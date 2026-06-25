<template>
  <div class="field-info-display">
    <!-- Field Title -->
    <div v-if="showTitle && Boolean(model.title || model.label)" class="mb-3">
      <n-ellipsis class="mr-auto text-4 font-500 capitalize">
        <span>{{ model.title || model.label }}</span>
        <span v-if="model.required" class="n-form-item-label__asterisk mr-auto flex-1">
          &nbsp;*
        </span>
      </n-ellipsis>
    </div>

    <!-- Field Details -->
    <n-descriptions
      :column="2"
      label-placement="left"
      class="mb-3 w-full whitespace-nowrap"
      label-class="property-label"
      content-class="!vertical-middle inline-block max-w-full"
    >
      <n-descriptions-item v-if="Boolean(model.label)" :label="$t('common.field')" :span="spanRecord.label">
        <n-tag class="wrapped-tag w-full">
          <n-ellipsis class="text-3 font-normal">
            {{ model.label }}
          </n-ellipsis>
        </n-tag>
      </n-descriptions-item>
      <n-descriptions-item v-if="ajvInfo?.schema?.type" :label="$t('common.type')" :span="spanRecord.type">
        <n-tag class="wrapped-tag w-full" :type="typeMap[ajvInfo.schema.type]">
          <n-ellipsis class="text-3 font-normal">
            {{ ajvInfo?.schema?.type }}
          </n-ellipsis>
        </n-tag>
      </n-descriptions-item>
      <n-descriptions-item v-if="ajvInfo?.schema?.default" :label="$t('common.default')" :span="spanRecord.default">
        <n-tag class="wrapped-tag">
          {{ ajvInfo?.schema?.default }}
        </n-tag>
      </n-descriptions-item>
      <n-descriptions-item
        v-if="ajvInfo?.schema?.description"
        :label="$t('common.description')"
        :span="2"
      >
        <div class="rounded-lg bg-gray-50 p-3">
          {{ ajvInfo.schema.description }}
        </div>
      </n-descriptions-item>
      <template v-if="hasEnum">
        <n-descriptions-item :label="$t('common.enum')" :span="spanRecord.enum" label-style="vertical-align: top!important" content-style="vertical-align: top!important">
          <ol class="ml-5 list-decimal">
            <li v-for="(enumItem, idx) in enumInfo.enum" :key="idx">
              <n-tag class="wrapped-tag mb-1 ml-1">
                {{ enumItem }}
              </n-tag>
            </li>
          </ol>
        </n-descriptions-item>
      </template>

      <template v-if="arrayItems">
        <n-descriptions-item :label="$t('common.arrayItems')" :span="spanRecord.arrayItems" label-style="vertical-align: top!important" content-style="vertical-align: top!important">
          <div class="rounded-lg bg-gray-50 p-3 !max-w-full dark:bg-gray-800">
            <div v-if="arrayItems.type" class="mb-2 max-w-full">
              <span class="mr-2 font-medium">{{ $t("common.type") }}:</span>
              <n-tag class="wrapped-tag" :type="typeMap[arrayItems.type]">
                {{ arrayItems.type }}
              </n-tag>
            </div>

            <div v-if="arrayItems.description" class="mb-2 max-w-full">
              <span class="mr-2 font-medium">{{ $t("common.description") }}:</span>
              <div class="mt-1 rounded-lg bg-gray-100 p-2">
                {{ arrayItems.description }}
              </div>
            </div>

            <div v-if="arrayItems.examples && arrayItems.examples.length" class="mb-2 max-w-full">
              <span class="mr-2 font-medium">{{ $t("common.examples") }}:</span>
              <ol class="ml-5 mt-1 list-decimal">
                <li v-for="(example, exampleIdx) in arrayItems.examples || []" :key="exampleIdx" class="mb-1">
                  <n-tag class="wrapped-tag max-w-full whitespace-pre-wrap break-all">
                    {{ example }}
                  </n-tag>
                </li>
              </ol>
            </div>

            <div v-if="arrayItems.airalogy_built_in_type" class="mb-2 max-w-full">
              <span class="mr-2 font-medium">{{ $t("common.airalogyType") }}:</span>
              <n-tag class="wrapped-tag" type="success">
                {{ arrayItems.airalogy_built_in_type }}
              </n-tag>
            </div>
            <div v-if="arrayItems.airalogy_type" class="mb-2 max-w-full">
              <span class="mr-2 font-medium">{{ $t("common.airalogyType") }}:</span>
              <n-tag class="wrapped-tag" type="success">
                {{ arrayItems.airalogy_type }}
              </n-tag>
            </div>

            <div v-if="arrayItems.format" class="mb-2 max-w-full">
              <span class="mr-2 font-medium">{{ $t("common.format") }}:</span>
              <n-tag class="wrapped-tag">
                {{ arrayItems.format }}
              </n-tag>
            </div>
          </div>
        </n-descriptions-item>
      </template>

      <template v-for="([propertyName, property]) in schemaProperties" :key="propertyName">
        <n-descriptions-item
          class="whitespace-nowrap"
          :label="propertyName"
          :span="spanRecord[propertyName]"
        >
          <ul v-if="Array.isArray(property)" class="ml-5 list-decimal">
            <li
              v-for="(propertyItem, propertyIndex) in property"
              :key="propertyIndex"
              class="mb-4 last:mb-0"
            >
              <n-tag v-if="typeof propertyItem === 'string'" class="min-h-fit">
                <div class="break-all text-wrap text-3">
                  {{ propertyItem }}
                </div>
              </n-tag>
              <div v-if="propertyItem.format" class="mt-2 max-w-20">
                <span class="mr-4 inline-block">{{ $t("common.format") }}:</span>
                <n-tag>
                  <n-ellipsis>
                    {{ propertyItem.format }}
                  </n-ellipsis>
                </n-tag>
              </div>
            </li>
          </ul>
          <n-tag v-else :type="typeMap[property]" class="wrapped-tag w-full">
            <n-ellipsis class="text-3 font-normal">
              {{ property }}
            </n-ellipsis>
          </n-tag>
        </n-descriptions-item>
      </template>
      <template v-if="model.assigner">
        <n-descriptions-item :label="$t('common.assignerMode')" :span="2">
          <n-tag class="wrapped-tag w-full">
            {{ model.assigner.mode }}
          </n-tag>
        </n-descriptions-item>
        <n-descriptions-item
          v-if="showAssignerDependencies"
          :label="$t('common.assignerDependencies')"
          :span="2"
          content-style="display: flex!important; flex-wrap: wrap; gap: 8px;"
        >
          <assigner-dependencies
            :fields="model.assigner.dependent_fields"
            :scope="scope"
            :var-scope-record="varScopeRecord"
            :is-var-table="isVarTable"
            :is-small="true"
            :show-label="false"
            :field-activation-status="{}"
            source="form"
          />
        </n-descriptions-item>
        <n-descriptions-item
          v-if="showAssignerTargets && model.dependent"
          label="Assigner targets"
          :span="2"
          content-style="display: flex!important; flex-wrap: wrap; gap: 8px;"
        >
          <assigner-dependencies
            :fields="model.dependent?.map(({ name }) => name) || []"
            title="Assigner targets:"
            :scope="scope"
            :var-scope-record="varScopeRecord"
            :is-var-table="isVarTable"
            :is-small="true"
            :show-label="false"
            :field-activation-status="{}"
            source="form"
          />
        </n-descriptions-item>
      </template>
    </n-descriptions>
  </div>
</template>

<script setup lang="ts">
import type { IFieldItem } from "@/views/project-protocols/modules/protocol/types/types"
import type { ScopeFieldKey } from "@airalogy/aimd-core/types"
import type { ValidateFunction } from "ajv"
import type { TagProps } from "naive-ui"
import AssignerDependencies from "@/components/custom/aimd/components/assigner-dependencies.vue"
import { noCase } from "@/utils/changeCase"
import { $t } from "@airalogy/shared/locales"

interface Props {
  model: IFieldItem
  scope?: ScopeFieldKey
  ajvInfo?: any
  enumInfo?: any
  typeMap?: Record<string, TagProps["type"]>
  varScopeRecord?: any
  isVarTable?: (prop: string) => boolean
  showTitle?: boolean
  showAssignerDependencies?: boolean
  showAssignerTargets?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showTitle: true,
  showAssignerDependencies: true,
  showAssignerTargets: true,
  typeMap: () => ({
    string: "default",
    number: "info",
    integer: "info",
    boolean: "success",
    array: "warning",
    object: "error",
  }),
})

const ajvInfo = toRef(props, "ajvInfo") as any as Ref<
  Omit<ValidateFunction, "schema"> & { schema?: Record<string, any> }
>

const hasEnum = computed(() => {
  return props.enumInfo && Array.isArray(props.enumInfo.enum) && props.enumInfo.enum.length > 0
})

const arrayItems = computed(() => {
  return ajvInfo.value?.schema?.items
})

const excludeKeys = ["title", "$defs", "description", "type", "default", "enum", "items"]
const schemaProperties = computed(() => {
  if (!ajvInfo.value?.schema) {
    return []
  }

  const entries = (Object.entries(ajvInfo.value.schema).filter(([key]) => !excludeKeys.includes(key)) as [string, any][]).map(([key, property]) => {
    if (key === "airalogy_built_in_type" || key === "airalogy_type") {
      return ["airalogy built-in type", property]
    }

    const convertedKey = noCase(key)

    return [convertedKey, property]
  })

  return entries
})

const spanRecord = computed(() => {
  const labelSpan = ajvInfo.value?.schema?.type ? 1 : hasEnum.value || ajvInfo.value?.schema ? 2 : 1
  const typeSpan = labelSpan === 1 ? 1 : 2
  const defaultSpan = schemaProperties.value.length > 1 ? 2 : 1
  const itemsSpan = 2 // Array items always get full width

  const record = {
    label: labelSpan,
    type: typeSpan,
    default: defaultSpan,
    items: itemsSpan,
    arrayItems: itemsSpan,
    enum: 2,
  } as Record<string, number>

  schemaProperties.value.forEach(([key, property]) => {
    if (Array.isArray(property)) {
      record[key] = 2
    }
    else {
      record[key] = 1
    }
  })

  return record
})
</script>

<style lang="sass" scoped>
.wrapped-tag
  @apply whitespace-pre-wrap break-all min-h-fit

:deep(.property-label)
  @apply vertical-middle! max-w-full inline-block

  &::first-letter
    text-transform: uppercase
</style>

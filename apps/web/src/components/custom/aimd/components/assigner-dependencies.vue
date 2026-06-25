<template>
  <div class="flex flex-wrap items-center gap-2">
    <span v-if="showLabel" class="mr-2">{{ title }}</span>
    <div
      v-for="field in fields"
      :key="field"
      class="aimd-field cursor-pointer !mt-0"
      :class="[
        { 'aimd-field--tooltip': isTooltip },
        { 'aimd-field--small': isSmall },
        { '!my-2': isTableForm },
        { 'aimd-field--active': getFieldActivationStatus(field) },
        { 'aimd-field--inactive': !getFieldActivationStatus(field) },
      ]"
      @click="handleClick(field)"
    >
      <span v-if="isVarTable(field)" class="aimd-field__scope aimd-field__scope--var_table"> var_table </span>
      <span
        v-else-if="scope"
        class="aimd-field__scope"
        :class="`aimd-field__scope--${scopeKeyRecord[varScopeRecord[field] as ScopeFieldKey]}`"
      >
        {{ scopeKeyRecord[varScopeRecord[field] as ScopeFieldKey] }}
      </span>
      <span v-else-if="isTableForm" class="aimd-field__scope aimd-field__scope--var-table-header">
        sub_var
      </span>
      <insert-wbr :text="field" class="aimd-field__name flex-1" />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ScopeFieldKey } from "@airalogy/aimd-core/types"
import InsertWbr from "@/components/common/insert-wbr.vue"
import { fieldEventKey } from "@airalogy/shared/constants/eventKey"
import { scopeKeyRecord } from "@airalogy/shared/utils"
import { useEventBus } from "@vueuse/core"

interface Props {
  fields: string[]
  scope?: string
  varScopeRecord?: Record<string, ScopeFieldKey>
  isTooltip?: boolean
  isSmall?: boolean
  isTableForm?: boolean
  showLabel?: boolean
  source?: "preview" | "form"
  isVarTable?: (prop: string) => boolean
  fieldActivationStatus?: Record<string, boolean>
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: "Assigner dependencies:",
  scope: "",
  varScopeRecord: () => ({}),
  tableRecord: () => ({}),
  isTooltip: false,
  isSmall: false,
  isTableForm: false,
  showLabel: true,
  isVarTable: () => false,
  fieldActivationStatus: () => ({}),
})

const fieldEventBus = useEventBus<string>(fieldEventKey)

// Computed property to get field activation status
const getFieldActivationStatus = computed(() => {
  return (field: string) => {
    // Default to false if status not provided
    return props.fieldActivationStatus?.[field] ?? false
  }
})

function handleClick(field: string) {
  fieldEventBus.emit("field-tag-focus", {
    scope: props.isTableForm ? "research_variable" : props.varScopeRecord[field],
    prop: field,
    autoBlur: true,
    source: props.source,
  })
}
</script>

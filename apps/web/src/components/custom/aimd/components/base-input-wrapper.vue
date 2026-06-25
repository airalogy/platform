<template>
  <template v-if="props.is">
    <component
      v-bind="{ ...$attrs, ...props.componentProps }"
      :is="props.is"
      ref="componentInstRef"
      class="max-h-full"
      :loading="isLoading && showAssigner"
    >
      <template v-if="showAssigner" #[props.prefixSlot]>
        <n-button
          type="primary"
          size="tiny"
          tertiary
          class="z-999 h-[calc(100%+12px)] w-[30px] -my-[6px] -ml-[10px]"
          @click.stop="handleClick"
        >
          <template #icon>
            <icon-ion-stop-circle-outline v-if="assignerLoadingRecord[props.prop]" align-items: center />
            <icon-local-calculator v-else />
          </template>
        </n-button>
      </template>
      <template v-if="props.assigner || props.dependent" #[props.assignerIconSlot]>
        <n-button
          v-if="isLoading && !showAssigner"
          type="primary"
          size="tiny"
          tertiary
          :theme-overrides="{ paddingTiny: '4px 4px' }"
          class="top-px"
          @click="handleAssignerCancel(props as any)"
        >
          <template #icon>
            <n-icon :size="14">
              <icon-ion-stop-circle-outline />
            </n-icon>
          </template>
        </n-button>
        <template v-else-if="props.assigner">
          <icon-local-cloud-done v-if="isLoading === false" />
          <icon-mdi-cloud-cancel-outline v-else color="var(--n-text-color-disabled)" />
        </template>
        <template v-else>
          <icon-local-cloud-upload />
        </template>
        <slot name="icon" />
      </template>
      <template v-for="(_, slotName) in $slots" :key="slotName" #[slotName]="slotData">
        <slot :name="slotName" v-bind="slotData" />
      </template>
    </component>
    <n-select
      v-if="props.anyOfSchemas && props.anyOfSchemas.length > 1"
      :value="selectedSchemaType"
      class="ml-2 max-w-fit"
      :options="schemaOptions"
      size="small"
      @update:value="handleSchemaChange"
    />
  </template>
  <div v-else v-bind="$attrs">
    {{ props.type }} not supported
  </div>
</template>

<script setup lang="ts">
import type { Component } from "vue"
import type { JsonSchema } from "../types/aimd-types"
import type { IAIMDInputProps } from "../types/props"
import { useSyncInputMirror } from "@airalogy/composables"
import CustomInputNumber from "../../custom-input-number/custom-input-number.vue"
import { useAIMDInject } from "../composables/useAIMDHelpers"

interface Props extends IAIMDInputProps {
  is: Component
  componentProps: any
  assignerIconSlot?: string
  prefixSlot?: string
  anyOfSchemas?: JsonSchema[]
}
defineOptions({
  inheritAttrs: false,
})

const props = withDefaults(defineProps<Props>(), {
  assignerIconSlot: "suffix",
  prefixSlot: "prefix",
})

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "schemaChange", schema: JsonSchema): void
}
const { assignerLoadingRecord, handleAssignerCancel, handleAssignerClick } = useAIMDInject()!
const isLoading = computed(() => {
  const { row, group } = props.info
  if (group) {
    return assignerLoadingRecord.value[`${group}.${props.prop}[${row}]`]
  }

  return assignerLoadingRecord.value[props.prop]
})

const componentInstRef = ref<any>(null)

const syncValueKey = ref(props.componentProps && "formattedValue" in props.componentProps ? "formattedValue" : "value")
const shouldSyncValueToMirror = ref(false)

const showAssigner = computed(() => {
  const { assigner, model } = props
  if (!assigner) {
    return false
  }

  const { mode } = assigner
  return mode === "manual"
    || (mode === "auto_first" && typeof model?.value === "undefined")
})

// Use the utility function to set up mirror synchronization
const componentProps = toRef(props, "componentProps")

function handleClick() {
  if (isLoading.value) {
    handleAssignerCancel(props as any)
  }
  else {
    handleAssignerClick(props as any)
  }
}

const schemaOptions = computed(() => {
  return props.anyOfSchemas?.map(schema => ({
    label: schema.type,
    value: schema.type,
  })) || []
})

const selectedSchemaType = ref(props.type)

function handleSchemaChange(type: string) {
  const selectedSchema = props.anyOfSchemas?.find(schema => schema.type === type)
  selectedSchemaType.value = type
  if (selectedSchema) {
    emit("schemaChange", selectedSchema)
  }
}

if (props.type && props.is !== CustomInputNumber) {
  useSyncInputMirror(componentInstRef, componentProps, syncValueKey, shouldSyncValueToMirror)
}

watch(componentInstRef, (value) => {
  if (value) {
    const { ref: handleRef } = props.componentProps
    handleRef(value)
  }
})
</script>

<style scoped lang="sass">
:deep(.n-input__input-mirror)
  white-space: nowrap!important
</style>

<template>
  <div class="h-full w-full" :class="anyOfSchemas && anyOfSchemas.length > 1 && 'flex flex-row items-center gap-2'">
    <!-- Use compact table file cell in var_table scope -->
    <template v-if="isUploadFileType(componentType)">
      <table-file-cell v-if="props.scope === 'var_table'" v-bind="props" />
      <file-input v-else v-bind="props" />
    </template>

    <div v-else-if="componentType === 'checkbox' " class="checkbox__wrapper my-auto self-start">
      <checkbox-input v-bind="props" />
    </div>

    <component :is="inputComponent" v-bind="{ ...props, onSchemaChange: handleSchemaChange }" v-else />
  </div>
</template>

<script setup lang="ts">
import type { IAIMDInputProps } from "@/components/custom/aimd/types/props"
import type { JsonSchema } from "../types/aimd-types"
import { useAnyOfSchemas } from "@/components/custom/aimd/composables/useInputProps"
import { BuiltInType } from "@airalogy/shared/enum/airalogy"
import { isUploadFileType } from "@airalogy/shared/utils"
import AnnotationInput from "./inputs/annotation-input.vue"
import BooleanSelectInput from "./inputs/boolean-select-input.vue"
import CheckboxInput from "./inputs/checkbox-input.vue"
import DatePickerInput from "./inputs/date-picker-input.vue"
import DynamicInput from "./inputs/dynamic-input.vue"
import EnumSelectInput from "./inputs/enum-select-input.vue"
import FileInput from "./inputs/file-input.vue"
import MdInput from "./inputs/md-input.vue"
import NumberInput from "./inputs/number-input.vue"
import RecordIdInput from "./inputs/record-id-input.vue"
import ResearchStepMinimalInput from "./inputs/research-step-minimal-input.vue"
import TableFileCell from "./inputs/table-file-cell.vue"
import TextInput from "./inputs/text-input.vue"
import TimePickerInput from "./inputs/time-picker-input.vue"

const props = defineProps<IAIMDInputProps>()

const { effectiveType, anyOfSchemas } = useAnyOfSchemas(props)
const componentType = ref(effectiveType.value)

const inputComponent = computed(() => {
  const { enumInfo } = props

  if (Array.isArray(enumInfo) || (!!enumInfo && Object.keys(enumInfo).length > 0)) {
    return EnumSelectInput
  }

  switch (componentType.value) {
    case "rs-annotation":
    case "rc-annotation":
      return AnnotationInput
    case "rs-minimal":
      return ResearchStepMinimalInput
    case "md":
    case BuiltInType.Md:
    case BuiltInType.AiralogyMarkdown:
      return MdInput
    case "text":
    case "textarea":
    case "password":
      return TextInput
    case BuiltInType.RecordId:
      return RecordIdInput
    case "integer":
    case "float":
    case "number":
      return NumberInput
    case "time":
    case "duration":
      return TimePickerInput
    case "date":
    case "datetime":
    case BuiltInType.CurrentTime:
      return DatePickerInput
    case "boolean":
      return BooleanSelectInput
    case "rs-check":
    case "rc-check":
    case "checkbox":
      return CheckboxInput
    case "array":
      return DynamicInput
    default:
      // File types are handled in template, but keep as fallback
      if (isUploadFileType(componentType.value)) {
        return FileInput
      }
      return TextInput
  }
})

function handleSchemaChange(schema: JsonSchema) {
  componentType.value = schema.type
}
</script>

<style scoped lang="sass">
.checkbox__wrapper
  border: 1px solid #e5e7eb
  width: 100%
  padding: 4px 10px
  border-radius: 0 0 6px 6px
  transition: all .3s cubic-bezier(.4, 0, .2, 1)
  background: rgb(247, 248, 249)

  &:hover
    border-color: #4181FD
    background: #fff

.input-group__input
  :deep(.n-input__input)
    border-left: 0
</style>

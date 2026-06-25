<template>
  <div class="h-full w-full" :class="anyOfSchemas && anyOfSchemas.length > 1 && 'flex flex-row items-center gap-2'">
    <asset-item v-if="props.model.value?.airalogy_file_id" :id="props.model.value?.airalogy_file_id" :type="(componentType as any)" :protocol-id="props.protocolId" />
    <asset-item v-else-if="props.info.file_extension && props.model.value" :id="props.model.value" :type="(componentType as any)" :protocol-id="props.protocolId" />

    <div v-else-if="componentType === 'checkbox' " class="checkbox__wrapper my-auto self-start">
      <checkbox-input v-bind="props" />
    </div>

    <component :is="inputComponent" v-bind="{ ...props, onSchemaChange: handleSchemaChange }" v-else />
  </div>
</template>

<script setup lang="ts">
import type { JsonSchema } from "@/components/custom/aimd/types/aimd-types"
import type { IAIMDInputProps } from "@/components/custom/aimd/types/props"
import AssetItem from "@/components/common/asset-item.vue"
import AnnotationInput from "@/components/custom/aimd/components/inputs/annotation-input.vue"
import BooleanSelectInput from "@/components/custom/aimd/components/inputs/boolean-select-input.vue"
import CheckboxInput from "@/components/custom/aimd/components/inputs/checkbox-input.vue"
import DatePickerInput from "@/components/custom/aimd/components/inputs/date-picker-input.vue"
import DynamicInput from "@/components/custom/aimd/components/inputs/dynamic-input.vue"
import EnumSelectInput from "@/components/custom/aimd/components/inputs/enum-select-input.vue"
import FileInput from "@/components/custom/aimd/components/inputs/file-input.vue"
import MdInput from "@/components/custom/aimd/components/inputs/md-input.vue"
import NumberInput from "@/components/custom/aimd/components/inputs/number-input.vue"
import ResearchCheckMinimalInput from "@/components/custom/aimd/components/inputs/research-check-minimal-input.vue"
import ResearchStepMinimalInput from "@/components/custom/aimd/components/inputs/research-step-minimal-input.vue"
import TextInput from "@/components/custom/aimd/components/inputs/text-input.vue"
import TimePickerInput from "@/components/custom/aimd/components/inputs/time-picker-input.vue"
import { useAnyOfSchemas } from "@/components/custom/aimd/composables/useInputProps"
import { BuiltInType } from "@airalogy/shared/enum/airalogy"

const props = defineProps<IAIMDInputProps & {
  protocolId: string
}>()

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
    case "rc-minimal":
      return ResearchCheckMinimalInput
    case "image":
    case "csv":
    case "file":
    case "video":
    case "audio":
    case "pdf":
      return FileInput
    case "array":
      return DynamicInput
    default:
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

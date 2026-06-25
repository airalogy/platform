<template>
  <base-input-wrapper
    :is="CustomCheckbox"
    v-bind="props"
    :component-props="customCheckboxProps"
    :any-of-schemas="anyOfSchemas"
    @schema-change="handleSchemaChange"
  />
</template>

<script setup lang="ts">
import type { JsonSchema } from "../../types/aimd-types"
import type { IAIMDInputProps } from "../../types/props"
import CustomCheckbox from "@/components/custom/custom-checkbox.vue"
import { useInputProps } from "../../composables/useInputProps"
import BaseInputWrapper from "../base-input-wrapper.vue"

const props = defineProps<IAIMDInputProps>()

const emit = defineEmits<IEmits>()

const { customCheckboxProps, anyOfSchemas, handleSchemaChange: innerHandleSchemaChange } = useInputProps(props)

interface IEmits {
  (e: "schemaChange", schema: JsonSchema): void
}

function handleSchemaChange(schema: JsonSchema) {
  innerHandleSchemaChange(schema)
  emit("schemaChange", schema)
}
</script>

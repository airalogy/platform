<template>
  <base-input-wrapper
    v-bind="props"
    :is="CustomInputNumber"
    :component-props="numberProps"
    :any-of-schemas="anyOfSchemas"
    @schema-change="handleSchemaChange"
  />
</template>

<script setup lang="ts">
import type { JsonSchema } from "../../types/aimd-types"
import type { IAIMDInputProps } from "../../types/props"
import CustomInputNumber from "@/components/custom/custom-input-number/custom-input-number.vue"
import { useInputProps } from "../../composables/useInputProps"
import BaseInputWrapper from "../base-input-wrapper.vue"

const props = defineProps<IAIMDInputProps>()

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "schemaChange", schema: JsonSchema): void
}

const { numberProps, handleSchemaChange: innerHandleSchemaChange, anyOfSchemas } = useInputProps(props)

function handleSchemaChange(schema: JsonSchema) {
  innerHandleSchemaChange(schema)
  emit("schemaChange", schema)
}
</script>

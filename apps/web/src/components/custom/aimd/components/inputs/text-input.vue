<template>
  <base-input-wrapper
    v-bind="props"
    :is="NInput"
    :component-props="inputProps"
    :any-of-schemas="anyOfSchemas"
    @schema-change="handleSchemaChange"
  />
</template>

<script setup lang="ts">
import type { JsonSchema } from "../../types/aimd-types"
import type { IAIMDInputProps } from "../../types/props"
import { NInput } from "naive-ui"
import { useInputProps } from "../../composables/useInputProps"
import BaseInputWrapper from "../base-input-wrapper.vue"

const props = defineProps<IAIMDInputProps>()

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "schemaChange", schema: JsonSchema): void
}

const { inputProps, handleSchemaChange: innerHandleSchemaChange, anyOfSchemas } = useInputProps(props)

function handleSchemaChange(schema: JsonSchema) {
  innerHandleSchemaChange(schema)
  emit("schemaChange", schema)
}
</script>

<template>
  <div class="border border-gray-200 rounded-b-md p-1">
    <base-input-wrapper
      v-bind="props"
      :is="DynamicInputHorizontal"
      :component-props="dynamicInputProps"
      :any-of-schemas="anyOfSchemas"
      class="flex-1"
      @schema-change="handleSchemaChange"
    />
  </div>
</template>

<script setup lang="ts">
import type { JsonSchema } from "../../types/aimd-types"
import type { IAIMDInputProps } from "../../types/props"
import { useInputProps } from "../../composables/useInputProps"
import BaseInputWrapper from "../base-input-wrapper.vue"
import DynamicInputHorizontal from "./dynamic-input-horizontal.vue"

const props = defineProps<IAIMDInputProps>()

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "schemaChange", schema: JsonSchema): void
}

const { dynamicInputProps, handleSchemaChange: innerHandleSchemaChange, anyOfSchemas } = useInputProps(props)

function handleSchemaChange(schema: JsonSchema) {
  innerHandleSchemaChange(schema)
  emit("schemaChange", schema)
}
</script>

<style scoped lang="sass">
</style>

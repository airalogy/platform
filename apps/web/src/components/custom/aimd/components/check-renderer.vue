<template>
  <div :id="`research_check-${name}`" class="aimd-field-wrapper aimd-field--checkbox">
    <div class="aimd-field-wrapper aimd-field-wrapper--text">
      <slot v-if="props.prefix" />
      <span
        :id="`research_check-${name}-check`"
        class="aimd-field-wrapper aimd-field--checkbox aimd-field--checkbox-research_check"
      >
        <aimd-item v-if="item" v-bind="item" />
      </span>
      <slot v-if="!props.prefix" />
    </div>
    <div
      v-if="annotationItem"
      :id="`research_check-${name}-annotation`"
      class="research-check__annotation"
    >
      <aimd-item v-bind="annotationItem" />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { VNode } from "vue"
import type { IAIMDItemProps } from "../types/aimd-types"
import AimdItem from "./aimd-item.vue"

const props = withDefaults(defineProps<{
  item: IAIMDItemProps | null
  annotationItem: IAIMDItemProps | null
  name: string
  content: VNode[]
  prefix?: boolean
}>(), {
  prefix: false,

})
</script>

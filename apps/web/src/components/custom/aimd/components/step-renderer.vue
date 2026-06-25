<template>
  <div class="research-step__item">
    <div :id="`research_step-${name}-header`" class="aimd-field-wrapper research-step__header">
      <tooltip-button
        quaternary
        size="tiny"
        :tooltip="collapse ? 'Click to show annotation input' : 'Click to hide annotation input'"
        :button-props="{ iconPlacement: 'right' }"
        class="-ml-1"
        @click="collapse = !collapse"
      >
        <template #default>
          <span class="research-step__sequence">Step {{ step }}</span>
        </template>
        <template #icon>
          <n-icon :class="collapse ? '-rotate-90' : ''" :component="ChevronDownIcon" />
        </template>
      </tooltip-button>
      <slot />
    </div>
    <div
      v-if="check"
      :id="`research_step-${name}-check`"
      class="aimd-field-wrapper aimd-field--checkbox mt-2"
    >
      <aimd-item v-if="item" v-bind="item" />
    </div>
    <div
      :id="`research_step-${name}`"
      class="aimd-field-wrapper aimd-field--tooltip research-step__annotation"
    >
      <!-- <component :is="annotationVnode" v-if="annotationVnode" /> -->
      <aimd-item v-if="props.annotationItem" v-bind="props.annotationItem" :class="collapse ? 'hidden' : ''" />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { VNode } from "vue"
import type { IAIMDItemProps } from "../types/aimd-types"
import TooltipButton from "@airalogy/components/src/tooltip-button.vue"
import ChevronDownIcon from "~icons/ion/chevron-down"
import { NIcon } from "naive-ui"
import { ref } from "vue"
import AimdItem from "./aimd-item.vue"

interface Props {
  item: IAIMDItemProps | null
  annotationItem: IAIMDItemProps | null
  check: any
  step?: string
  name: string
  content: VNode[]
}

const props = defineProps<Props>()

const initCollapsedVal = !props.annotationItem?.model?.value?.annotation
const collapse = ref(initCollapsedVal)

// const annotationVnode = props.annotationItem
//   ? h(
//     AIMDItem,
//     {
//       ...props.annotationItem,
//       class: collapse.value ? "hidden" : "",
//     },
//     undefined,
//   )
//   : undefined

// watch(collapse, (val) => {
//   if (annotationVnode && annotationVnode.component) {
//     annotationVnode.component.attrs.class = val ? "hidden" : ""
//   }
// })
</script>

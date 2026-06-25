<template>
  <div v-if="type === 'step-ref'" ref="fieldContainerRef" class="group relative cursor-pointer" @click="handleClick">
    <div
      class="absolute-x-center bottom-full nowrap-hidden border-1 rounded-2 bg-white opacity-0 transition group-hover:opacity-100"
    >
      <div class="aimd-field aimd-field--no-style aimd-field__label">
        <span class="aimd-field__scope" :class="`aimd-field__scope--${type}`"> {{ scope }}</span>
        <insert-wbr :text="prop" class="aimd-field__name flex-1" />
      </div>
      <div class="break-all p-1 text-wrap">
        {{ info.suffix }}
      </div>
    </div>
    <a
      class="cursor-pointer font-bold !text-inherit !underline !underline-2 !underline-amber"
      :href="`#research_step-${prop}-header`"
    >
      {{ model.value }}
    </a>
  </div>
  <div v-else-if="type === 'rv-ref'" ref="fieldContainerRef" class="group relative cursor-pointer" @click="handleClick">
    <div
      class="absolute-x-center bottom-full nowrap-hidden border-1 rounded-2 bg-white opacity-0 transition group-hover:opacity-100"
    >
      <div class="aimd-field aimd-field--no-style aimd-field__label">
        <span class="aimd-field__scope" :class="`aimd-field__scope--${type}`"> {{ scope }}</span>
        <insert-wbr :text="prop" class="aimd-field__name flex-1" />
      </div>
      <div class="break-all p-1 text-wrap">
        {{ info.description || title || prop }}
      </div>
    </div>
    <a
      class="cursor-pointer font-bold !text-inherit !underline !underline-2 !underline-[#1A79FF]"
      :href="`#research_variable-${prop}`"
    >
      {{ model.value }}
    </a>
  </div>
  <var-table-wrapper
    v-else-if="type === 'var-table-wrapper'"
    :disabled="disabled"
    :info="(info as any)"
    :model="model.value"
    :scope="scope"
  />
</template>

<script setup lang="ts">
import type { BubbleMenuEventName, BubbleMenuEventPayload } from "@airalogy/composables"
import type { IAIMDItemProps } from "../types/aimd-types"
import InsertWbr from "@/components/common/insert-wbr.vue"
import { bubbleMenuEventKey } from "@airalogy/shared/constants/eventKey"
import { useEventBus } from "@vueuse/core"
import { toRefs } from "vue"
import VarTableWrapper from "./table/var-table-wrapper.vue"

const props = defineProps<IAIMDItemProps>()
const { type, scope, prop, model, info, title, disabled } = toRefs(props)

const fieldContainerRef = ref<HTMLElement | null>(null)
const bubbleMenuEvent = useEventBus<BubbleMenuEventName, BubbleMenuEventPayload>(bubbleMenuEventKey)

function handleClick(event: MouseEvent) {
  const { prop, scope, type } = props

  bubbleMenuEvent.emit("triggerBubbleMenu", { dom: fieldContainerRef.value, data: { prop, scope, type } })
}
</script>

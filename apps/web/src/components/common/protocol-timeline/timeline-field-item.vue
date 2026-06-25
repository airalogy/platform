<template>
  <div>
    <!-- Special tag types: step-ref, rv-ref, var-table-wrapper -->
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
    />

    <!-- Regular field item -->
    <div v-else class="timeline-field-item" :class="props.contentClass">
      <!-- Custom form item layout without n-form-item -->
      <div v-if="scope === 'research_variable'" ref="fieldContainerRef" class="aimd-field aimd-field--no-style aimd-field__label cursor-pointer" @mouseenter="handleShowBubbleMenu">
        <span class="aimd-field__scope" :class="`aimd-field__scope--${type}`"> {{ fieldType }} </span>
        <insert-wbr :text="prop" class="aimd-field__name flex-1" />
      </div>

      <!-- Content area -->
      <div class="timeline-field-item__content">
        <n-tooltip ref="tooltipRef" placement="top-start" trigger="hover" style="max-width: 600px">
          <template #trigger>
            <timeline-input v-bind="props" :class="props.model.value?.airalogy_file_id ? 'timeline-field-item__wrapper' : ''" />
          </template>

          <div>
            <span>{{ tooltip || prop }}</span>
            <div v-if="assigner">
              <div>
                <span>{{ $t("common.assignerMode") }}: </span>
                <n-tag size="small">
                  {{ assigner.mode }}
                </n-tag>
              </div>
              <assigner-dependencies
                :fields="assigner.dependent_fields"
                :scope="scope"
                :var-scope-record="varScopeRecord"
                :is-tooltip="true"
                :is-var-table="isVarTable"
                source="preview"
              />
            </div>
          </div>
        </n-tooltip>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { BubbleMenuEventName, BubbleMenuEventPayload } from "@airalogy/composables/useBubbleMenu"
import type { TooltipInst } from "naive-ui"
import type { IAIMDItemProps } from "../../custom/aimd/types/aimd-types"
import InsertWbr from "@/components/common/insert-wbr.vue"
import TimelineInput from "@/components/common/protocol-timeline/timeline-input.vue"
import AssignerDependencies from "@/components/custom/aimd/components/assigner-dependencies.vue"
import VarTableWrapper from "@/components/custom/aimd/components/table/var-table-wrapper.vue"
import { useAIMDInject } from "@/components/custom/aimd/composables/useAIMDHelpers"
import { bubbleMenuEventKey } from "@/utils/template/eventKey"
import { $t } from "@airalogy/shared/locales"
import { useEventBus } from "@vueuse/core"

const props = defineProps<IAIMDItemProps & {
  protocolId: string
  contentClass?: string
}>()

const { type, scope, prop, model, assigner, required, tooltip, fieldType, info, title, disabled } = toRefs(props)

const { isVarTable, varScopeRecord, assignerLoadingRecord } = useAIMDInject()!

const fieldContainerRef = ref<HTMLElement | null>(null)
const bubbleMenuEvent = useEventBus<BubbleMenuEventName, BubbleMenuEventPayload>(bubbleMenuEventKey)
const tooltipRef = ref<TooltipInst | null>(null)

provide("tooltipRef", tooltipRef)

function handleShowBubbleMenu(event: MouseEvent) {
  bubbleMenuEvent.emit("triggerBubbleMenu", { dom: fieldContainerRef.value, data: { prop, scope, type } })
}

function handleClick(event: MouseEvent) {
  const { prop, scope, type } = props
  bubbleMenuEvent.emit("triggerBubbleMenu", { dom: fieldContainerRef.value, data: { prop, scope, type } })
}
</script>

<style scoped lang="sass">
.timeline-field-item

  @apply max-w-full w-fit

  &__wrapper
    border: 1px solid rgb(224, 224, 230)
    border-radius: 0 0 4px 4px

  &__content
    position: relative

// Custom error styling without form item context
.timeline-field-item--error
  .timeline-field-item__content
    &::after
      content: ""
      position: absolute
      bottom: -2px
      left: 0
      right: 0
      height: 1px
      background: #d03050

:deep(.n-input__placeholder)
  word-break: break-all!important
:deep(.n-form-item-blank)
  --n-blank-height: fit-content
:deep(.n-input__textarea-el)
  padding: 0!important
:deep(.n-input-wrapper)
  padding: 6px 10px
:deep(.n-form-item-label__asterisk)
  position: absolute
  left: -10px
:deep(.n-checkbox__label)
  flex: 1
  display: inline-flex
  align-items: center
:deep(.n-base-selection-label)
  min-height: 34px

:deep(.n-upload-file-info .n-image)
  min-height: 51px
:deep(.n-upload-trigger.n-upload-trigger--image-card)
  width: 100%
:deep(.n-upload-file-list.n-upload-file-list--grid)
  grid-template-columns: repeat(auto-fit, minmax(96px, 1fr))

:deep(.upload__wrapper--padding .n-upload-file-info__thumbnail)
  padding: 24px 0

:deep(.upload__wrapper--no-padding .n-upload-file-info__thumbnail)
  min-width: 20rem

:global(.aimd-field__table .n-input)
  width: 100%!important

:deep(.n-upload-file-list .n-upload-file.n-upload-file--image-card-type .n-progress)
  bottom: auto!important
  top: 8px!important
</style>

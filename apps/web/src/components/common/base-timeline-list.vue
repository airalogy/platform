<template>
  <n-timeline
    v-if="list.length > 0"
    size="large"
    :icon-size="iconSize"
  >
    <n-timeline-item
      v-for="(item, idx) in list"
      :key="item.time"
      :style="[idx === 0 && '--item-top: 0', itemStyle]"
      class="pb-4" :class="itemClass"
    >
      <div
        class="absolute top-0 flex flex-col justify-center text-xl color-[#1A79FF] -left-14 -top-1" :class="[labelClass]"
        :style="labelStyle"
      >
        <div class="mb-3 text-center">
          <slot name="prefix" :item="item" :index="idx">
            <span class="mr-2">#</span>{{ item.order }}
          </slot>
        </div>
        <slot name="actions" :item="item" :index="idx" />
      </div>

      <slot v-if="showHeader" name="header" :item="item" :index="idx">
        <n-button
          class="absolute-tr z-100 -top-2.5"
          type="primary"
          quaternary
          @click="emit('showDetail', item)"
        >
          View Detail
        </n-button>
      </slot>

      <div
        class="w-full pl-5"
        :class="[{ 'relative h-50 overflow-hidden': collapsedItem[item.id] }, contentClass]"
      >
        <slot name="content" :item="item" :index="idx" />
      </div>

      <slot name="footer" :item="item" :index="idx">
        <div
          v-if="collapsedItem[item.id]"
          class="absolute-bl h-fit w-full flex justify-center bg-gradient-from-white bg-gradient-to-transparent bg-gradient-linear bg-gradient-to-t pt-10"
        >
          <n-button
            type="primary"
            quaternary
            icon-placement="right"
            @click="() => (collapsedItem[item.id] = false)"
          >
            {{ $t("common.more") }}
            <template #icon>
              <icon-local-dropdown-outline />
            </template>
          </n-button>
        </div>
      </slot>
    </n-timeline-item>
  </n-timeline>
</template>

<script setup lang="ts" generic="T extends { id: string | number, time: string | number, order: number | string}">
import type { HTMLAttributes } from "vue"
import { $t } from "@airalogy/shared/locales"

// eslint-disable-next-line ts/consistent-type-definitions
type Emits = {
  (e: "showDetail", item: T): void
  (e: "updateCollapsedItem", item: T, collapsed: boolean): void
}

const props = withDefaults(defineProps<{
  list: T[]
  collapsedItem: Record<string | number, boolean>
  itemClass?: HTMLAttributes["class"]
  itemStyle?: HTMLAttributes["style"]
  labelClass?: HTMLAttributes["class"]
  labelStyle?: HTMLAttributes["style"]
  iconSize?: number
  showHeader?: boolean
  contentClass?: HTMLAttributes["class"]
}>(), {
  showHeader: false,
})
const emit = defineEmits<Emits>()

const collapsedItem = useVModel(props, "collapsedItem", emit)

const circleOutlineSize = computed(() => Math.round((props.iconSize || 14) * 0.15))
const circleBorderSize = computed(() => Math.round((props.iconSize || 14) * 0.12))
const circleShadowSize = computed(() => Math.round((props.iconSize || 14) * 0.25))
</script>

<style scoped lang="sass">
:deep(.n-timeline-item-timeline__circle)
  background-color: #1A79FF
  border: v-bind('`${circleBorderSize}px solid #EDF4FF`')!important
  outline: v-bind('`${circleOutlineSize}px solid #FFFFFF`')
  box-shadow: v-bind('`0 0 0 ${circleShadowSize}px #E7EFFF`')
  position: relative
  &::before
    content: ''
    position: absolute
    top: var(--item-top, -7px)
    left: calc(50% - 1px)
    bottom: var(--item-bottom, -7px)
    width: 2px
    background-color: rgba(26, 121, 255, 0.3)
    box-shadow: 0 0 5px 0px rgba(26, 121, 255, 1)

:deep(.n-timeline-item-timeline__line)
  top: calc(var(--n-icon-size) + 4px)!important
:deep(.n-timeline .n-timeline-item:last-child .n-timeline-item-timeline .n-timeline-item-timeline__line)
  border-radius: 0 0 50% 50%
  background: linear-gradient(to bottom, #1A79FF, transparent)
  display: block
</style>

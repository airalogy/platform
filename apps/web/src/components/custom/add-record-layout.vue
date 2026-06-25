<template>
  <n-split v-bind="splitProps" v-model:size="splitSize">
    <template #1>
      <component :is="props.wrapper" v-if="props.wrapper">
        <slot name="prefix" />
        <n-tabs
          v-model:value="selectedTab" placement="left" type="card"
          :theme-overrides="props.themeOverrides"
          tab-class="bg-white" class="h-full w-full" pane-class="!h-full overflow-y-auto"
        >
          <template #prefix>
            <n-button quaternary class="mb-2.5" @click="handleToggle">
              <template #icon>
                <n-icon size="24">
                  <icon-local-menu-collapsed v-if="isCollapsed" />
                  <icon-local-menu-expand v-else />
                </n-icon>
              </template>
            </n-button>
          </template>
          <slot name="tabs" />
        </n-tabs>
      </component>
      <n-tabs
        v-else
        v-model:value="selectedTab" placement="left" type="card"
        :theme-overrides="props.themeOverrides"
        tab-class="bg-white" class="h-full w-full" pane-class="!h-full overflow-y-auto"
      >
        <template #prefix>
          <n-button quaternary class="mb-2.5" @click="handleToggle">
            <template #icon>
              <n-icon size="24">
                <icon-local-menu-collapsed v-if="isCollapsed" />
                <icon-local-menu-expand v-else />
              </n-icon>
            </template>
          </n-button>
        </template>
        <slot name="tabs" />
      </n-tabs>
    </template>
    <template #2>
      <div class="h-full w-full overflow-y-auto" :class="props.contentClass">
        <slot name="content" />
        <n-back-top v-if="showBackTop" />
      </div>
    </template>
    <template #resize-trigger>
      <div v-if="!isCollapsed" class="n-split__resize-trigger h-full w-full" />
    </template>
  </n-split>
</template>

<script setup lang="ts">
import type { Component } from "vue"

defineOptions({ name: "AddRecordLayout" })

const props = withDefaults(defineProps<IProps>(), {
  defaultSpiltSize: 0.35,
  collapsed: false,
  domMounted: false,
  themeOverrides: () => ({
    panePaddingMedium: "0 0 0 0",
    barColor: "transparent",
    tabGapMediumCardVertical: "10px",
    tabColor: "#fff",
    tabPaddingVerticalMediumCard: "0",
    tabBorderColor: "transparent",
  }),
  showBackTop: true,
  selectedTab: undefined,
  contentClass: "",
})

const emit = defineEmits<{
  (e: "update:splitSize", payload: string | number): void
  (e: "update:collapsed", payload: boolean): void
  (e: "update:selectedTab", payload: string | undefined): void
}>()

interface IProps {
  defaultSpiltSize?: number
  collapsed?: boolean
  domMounted?: boolean
  themeOverrides?: Record<string, any>
  showBackTop?: boolean
  selectedTab?: string
  wrapper?: Component
  contentClass?: string
}

const isCollapsed = useVModel(props, "collapsed")
const selectedTab = useVModel(props, "selectedTab")
const splitSize = ref(props.defaultSpiltSize)

watch(
  splitSize,
  (val) => {
    if (isCollapsed.value && val > 0) {
      isCollapsed.value = false
    }
    emit("update:splitSize", val)
  },
)

watch(isCollapsed, (val) => {
  if (val) {
    splitSize.value = 0
  }
  else {
    splitSize.value = props.defaultSpiltSize
  }
})

const splitProps = computed(() => {
  if (isCollapsed.value) {
    return { min: 0, max: 1, defaultSize: 0 }
  }

  return { min: 0.35, max: 0.65, defaultSize: props.defaultSpiltSize }
})

function handleToggle() {
  if (isCollapsed.value) {
    handleExpand()
  }
  else {
    handleCollapse()
  }
}

function handleExpand() {
  splitSize.value = props.defaultSpiltSize
  isCollapsed.value = false
}

function handleCollapse() {
  splitSize.value = 0
  isCollapsed.value = true
}

defineExpose({
  toggle: () => {
    if (isCollapsed.value) {
      splitSize.value = props.defaultSpiltSize
    }
    else {
      splitSize.value = 0
    }
    isCollapsed.value = !isCollapsed.value
  },
})
</script>

<style scoped lang="sass">
:deep(.n-tabs-nav-scroll-wrapper)
  &:before,&:after
    display: none

:deep(.n-tabs-nav--segment-type)
  position: relative
  margin: 20px 24px

:deep(.n-tabs-tab--active)
  --n-tab-text-color-hover: var(--n-tab-text-color-active)

:deep(.n-tabs-rail)
  padding: 0

:deep(.n-split-pane-1)
  min-width: 60px
</style>

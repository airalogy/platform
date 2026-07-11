<template>
  <header class="pt-5">
    <slot name="breadcrumb">
      <global-breadcrumb />
    </slot>
    <slot name="title">
      <div class="mt-5 flex items-center">
        <component :is="props.titleIcon" v-if="props.titleIcon" class="mr-4" />
        <h2 class="!text-6" :class="{ 'list__title ml-4 mt-3': !props.titleIcon }">
          {{ titleText }}
        </h2>
      </div>
    </slot>
  </header>

  <n-spin v-if="props.showGlobalSpin" :show="props.loading" content-class="size-full">
    <slot>
      <div class="min-w-0 flex flex-col">
        <n-tabs v-if="Array.isArray(props.tabs) && props.tabs.length > 0" :value="activeTab" v-bind="props.tabsProps" type="line" :class="props.wrapperClass" :style="props.wrapperStyle" @update:value="handleTabChange">
          <template #prefix>
            <slot name="prefix" />
          </template>
          <template #suffix>
            <slot name="suffix" />
          </template>
          <template v-for="(pane, index) in props.tabs" :key="resolvePaneName(pane, index)">
            <n-tab-pane
              :name="resolvePaneName(pane, index)"
              :tab="pane.tab"
              :disabled="pane.disabled"
              :closable="pane.closable"
              :display-directive="pane.displayDirective"
              :tab-props="pane.tabProps"
            >
              <global-content :show-spin="props.showContentSpin" />
            </n-tab-pane>
          </template>
        </n-tabs>
      </div>
    </slot>
  </n-spin>
  <slot v-else>
    <div class="min-w-0 flex flex-col">
      <n-tabs v-if="Array.isArray(props.tabs) && props.tabs.length > 0" :value="activeTab" v-bind="props.tabsProps" type="line" :class="props.wrapperClass" :style="props.wrapperStyle" @update:value="handleTabChange">
        <template #prefix>
          <slot name="prefix" />
        </template>
        <template #suffix>
          <slot name="suffix" />
        </template>
        <template v-for="(pane, index) in props.tabs" :key="resolvePaneName(pane, index)">
          <n-tab-pane
            :name="resolvePaneName(pane, index)"
            :tab="pane.tab"
            :disabled="pane.disabled"
            :closable="pane.closable"
            :display-directive="pane.displayDirective"
            :tab-props="pane.tabProps"
          >
            <global-content :show-spin="props.showContentSpin" />
          </n-tab-pane>
        </template>
      </n-tabs>
    </div>
  </slot>
</template>

<script setup lang="ts">
import type { TabPaneProps, TabsProps } from "naive-ui/es/tabs"
import type { Component, StyleValue } from "vue"

import GlobalBreadcrumb from "@/components/common/global-breadcrumb.vue"

import { useRouterPush } from "@/composables/useRouterPush"
import { defaultTabsProps } from "@/constants/content-layout"
import GlobalContent from "@/layouts/modules/global-content/index.vue"
import { $t } from "@airalogy/shared/locales"

defineOptions({ name: "ContentLayout" })

const props = withDefaults(defineProps<IProps>(), {
  title: "",
  tabs: () => [] as TabPaneProps[],
  tabsProps: () => defaultTabsProps,
  wrapperClass: "size-full min-w-0 flex-1",
  wrapperStyle: "",
  initialActiveTab: null,
  showGlobalSpin: false,
})

interface IProps {
  title?: string
  tabs?: TabPaneProps[]
  tabsProps?: TabsProps
  wrapperClass?: string
  wrapperStyle?: StyleValue
  initialActiveTab?: App.Global.TabKey | null
  loading?: boolean
  mapTabName?: (tabName: App.Global.TabKey) => App.Global.TabKey
  titleIcon?: Component
  showGlobalSpin?: boolean
  showContentSpin?: boolean
}

const route = useRoute()
const { routerPushByKey } = useRouterPush()

const activeTab = ref<App.Global.TabKey>(
  props.initialActiveTab || (route.name as App.Global.TabKey),
)

const titleText = computed(() => props.title || $t("page.home.dashboardTitle"))

function resolvePaneName(pane: TabPaneProps, index: number): string | number {
  if (pane.name !== undefined) {
    return pane.name
  }
  if (typeof pane.tab === "string" || typeof pane.tab === "number") {
    return pane.tab
  }
  return `tab-${index}`
}

async function handleTabChange(val: App.Global.TabKey) {
  const target = props.mapTabName ? props.mapTabName(val) : val
  const params: Record<string, string> = {}
  const routeParams = route.params as Record<string, string | undefined>
  if (routeParams.labUid) {
    params.labUid = routeParams.labUid
  }
  if (routeParams.projectUid) {
    params.projectUid = routeParams.projectUid
  }
  if (routeParams.groupId) {
    params.groupId = routeParams.groupId
  }
  if (routeParams.protocolUid) {
    params.protocolUid = routeParams.protocolUid
  }
  if (routeParams.questionId) {
    params.questionId = routeParams.questionId
  }

  await routerPushByKey(target, Object.keys(params).length ? { params } : undefined)
}

watch(
  () => route.name,
  async (key) => {
    await nextTick()
    const routeName = key as App.Global.TabKey
    if (key === "protocol-discussion-detail") {
      activeTab.value = "protocol-discussions"
    }
    else if (key === "protocol-info-apply-protocol") {
      activeTab.value = "protocol-detail" as any
    }
    else if (routeName) {
      activeTab.value = routeName
    }
  },
  { immediate: true },
)

const tabsBarStyle = computed(() => {
  const { placement } = props.tabsProps || {}
  if (placement === "left") {
    return { height: "auto", width: "4px" }
  }

  return { height: "4px", width: "auto" }
})
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
@use "@styles/sass/tab.sass" as *

:deep(.n-tabs-bar)
  height: v-bind("tabsBarStyle.height")
  width: v-bind("tabsBarStyle.width")
  border-radius: 10px!important

:deep(.n-tabs.n-tabs--left .n-tabs-bar)
  right: auto
  left: 0
  width: 4px
  border-radius: 4px 0 0 4px
</style>

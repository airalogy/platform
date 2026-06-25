<template>
  <div :class="props.wrapperClass" :style="props.wrapperStyle">
    <n-tabs
      v-model:value="activeTab"
      v-bind="props.tabsProps"
      type="line"
      @update:value="handleTabChange"
    >
      <template #prefix>
        <slot name="prefix" />
      </template>
      <template #suffix>
        <slot name="suffix" />
      </template>
      <template v-for="pane in props.tabs" :key="pane.name">
        <n-tab-pane v-bind="pane">
          <global-content />
        </n-tab-pane>
      </template>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import type { TabPaneProps, TabsProps } from "naive-ui/es/tabs"
import type { StyleValue } from "vue"
import { useRouterPush } from "@/composables/useRouterPush"
import GlobalContent from "@/layouts/modules/global-content/index.vue"

interface IProps {
  wrapperClass?: string
  wrapperStyle?: StyleValue
  tabsProps: TabsProps
  tabs: (TabPaneProps & { name: App.Global.TabKey })[]
}

const props = defineProps<IProps>()

const route = useRoute()
const activeTab = ref<string>(route.name as string)

const { routerPushByKey } = useRouterPush()
function handleTabChange(key: App.Global.TabKey) {
  const username = route.params.username
  routerPushByKey(
    key,
    typeof username === "string" ? { params: { username } } : undefined,
  )
}

watch(() => route.name, (val) => {
  activeTab.value = val as string
})
</script>

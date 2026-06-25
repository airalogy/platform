<template>
  <n-tabs
    v-model:value="activeTab"
    placement="top"
    :theme-overrides="defaultTabsProps.themeOverrides"
    :bar-width="70"
    tab-class="rounded hover:bg-[#EDEFF4] !px-3"
    pane-class="overflow-visible"
    type="line"
    @update:value="handleTabChange"
  >
    <n-tab-pane name="overview" tab="Overview">
      <overview-tab />
    </n-tab-pane>

    <n-tab-pane name="versions" tab="Version History">
      <version-history-tab />
    </n-tab-pane>

    <n-tab-pane name="qa" tab="Q & A">
      <qa-tab @ask-question="handleAskQuestion" />
    </n-tab-pane>

    <n-tab-pane name="records" tab="Records">
      <records-tab />
    </n-tab-pane>
  </n-tabs>
</template>

<script setup lang="ts">
import { defaultTabsProps } from "@/constants/content-layout"
import OverviewTab from "./tabs/overview-tab.vue"
import QaTab from "./tabs/qa-tab.vue"
import RecordsTab from "./tabs/records-tab.vue"
import VersionHistoryTab from "./tabs/version-history-tab.vue"

const props = defineProps<{
  content: string
  tags: string[]
}>()

const emit = defineEmits<{
  (e: "tabChange", tab: string): void
  (e: "askQuestion"): void
  (e: "writeReview"): void
}>()

const activeTab = ref("overview")

function handleTabChange(value: string) {
  activeTab.value = value
  emit("tabChange", value)
}

function handleAskQuestion() {
  emit("askQuestion")
}
</script>

<style scoped lang="sass">
@use "@styles/sass/tab.sass" as *

:deep(.n-tabs-bar)
  height: 4px
</style>

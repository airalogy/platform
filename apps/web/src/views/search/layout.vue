<template>
  <global-layout>
    <content-layout :tabs="tabs" title="Search" initial-active-tab="search-protocol" :title-icon="SearchIcon" />
  </global-layout>
</template>

<script setup lang="ts">
import type { TabPaneProps } from "naive-ui/es/tabs"
import SearchBaseIcon from "@/components/icon/search-icon.vue"
import ContentLayout from "@/layouts/content-layout/index.vue"
import GlobalLayout from "@/layouts/global-layout/index.vue"

function SearchIcon() {
  return h(SearchBaseIcon, { color: "rgb(var(--primary-color))", size: 40 })
}

const tabs: Ref<TabPaneProps[]> = ref([
  { name: "search-protocol", tab: "Protocol" },
  { name: "search-record", tab: "Record" },
  { name: "search-discussion", tab: "Discussion" },
])
</script>

<style scoped>
.hover\:router-link:hover {
  text-decoration: underline;
  color: var(--primary-color);
}
</style>

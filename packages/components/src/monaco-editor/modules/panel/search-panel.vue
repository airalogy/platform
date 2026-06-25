<template>
  <div class="h-full flex flex-col">
    <n-input v-model:value="searchQuery" placeholder="Search..." class="mb-4" />
    <n-list class="flex-1 overflow-y-auto">
      <n-list-item v-for="result in searchResults" :key="result.id">
        <!-- Result content will go here -->
        {{ result }}
      </n-list-item>
      <n-empty v-if="!searchResults.length" description="No results found" />
    </n-list>
  </div>
</template>

<script setup lang="ts">
import MiniSearch from "minisearch"
import { NEmpty, NInput, NList, NListItem } from "naive-ui"
import { computed, ref, watch } from "vue"

interface Props {
  data: any[]
  options: any
}

const props = defineProps<Props>()

const searchQuery = ref("")
const miniSearch = ref<MiniSearch | null>(null)

watch(() => props.data, (newData) => {
  if (newData) {
    miniSearch.value = new MiniSearch(props.options)
    miniSearch.value.addAll(newData)
  }
}, { immediate: true })

const searchResults = computed(() => {
  if (!searchQuery.value || !miniSearch.value) {
    return []
  }
  return miniSearch.value.search(searchQuery.value)
})
</script>

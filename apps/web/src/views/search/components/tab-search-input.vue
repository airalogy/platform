<template>
  <n-form :show-lable="false" :show-feedback="false">
    <n-grid :x-gap="24">
      <n-form-item-gi :span="8" :show-label="false">
        <search-input @submit:search="handleSearch" />
      </n-form-item-gi>
      <n-form-item-gi :span="8" :show-label="false">
        <search-filter-actions
          :type="props.activeTab"
          class="size-full"
          @update:filters="handleFilterUpdate"
        />
      </n-form-item-gi>
    </n-grid>
  </n-form>

  <!-- Search Results Section -->
  <n-divider class="!my-3" />
</template>

<script setup lang="ts">
import SearchInput from "@/components/common/search-input.vue"
import SearchFilterActions from "./search-filter-actions.vue"

const props = defineProps<{
  activeTab: "protocol" | "record" | "discussion"
  loading?: boolean
}>()

const emits = defineEmits<IEmits>()

interface IEmits {
  (e: "submit:search", val: string): void
  (e: "update:loading", loading: boolean): void
  (e: "update:filters", filters: {
    dateRange?: [number, number] | null
    userIds?: string[]
    tags?: string[]
  }): void
}

function handleSearch(val: string) {
  emits("submit:search", val)
}

function handleFilterUpdate(filters: {
  dateRange?: [number, number] | null
  userIds?: string[]
  tags?: string[]
}) {
  emits("update:filters", filters)
}
</script>

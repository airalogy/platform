<template>
  <div>
    <search-input v-bind="props.inputProps" @submit:search="handleSearch" />
    <n-modal
      v-model:show="isSearchModalShow"
      preset="card"
      :title="`${searchResult.total_count} result${searchResult.total_count > 1 ? 's' : ''}`"
      :bordered="false"
      size="huge"
      class="w-160"
      @after-leave="restoreSearch"
    >
      <n-spin :show="isSearchLoading" class="min-h-15 w-full">
        <div v-if="searchResult.total_count > 0">
          <slot name="result">
            <!-- <router-link
              v-for="item in searchResult.data"
              :key="(item as Api.Search.SearchItem).name"
              :to="(item as Api.Search.SearchItem).name"
              class="my-2 block w-fit text-left hover:router-link"
            >
              {{ (item as Api.Search.SearchItem).name }}
            </router-link> -->
          </slot>
        </div>
        <div v-else class="h-15 w-full text-center text-lg color-gray leading-15">
          No search result.
        </div>
      </n-spin>
    </n-modal>
  </div>
</template>

<script setup lang="ts" generic="T extends unknown">
import type { IProps as ISearchInputProps } from "@/components/common/search-input.vue"
import { request } from "@/service/request"

import { useBoolean } from "@airalogy/composables"

const props = defineProps<{
  onSubmit?: (val: string) => Promise< Api.GetResponse<T> | null>
  inputProps?: ISearchInputProps
}>()

const emits = defineEmits<{
  (e: "search:result", val: Api.GetResponse<T>): void
  (e: "modal:close"): void
  (e: "modal:open"): void
}>()

const {
  bool: isSearchModalShow,
  setFalse: hideSearchModal,
  setTrue: showSearchModal,
} = useBoolean()

const {
  bool: isSearchLoading,
  setFalse: stopSearchLoading,
  setTrue: startSearchLoading,
} = useBoolean()

const searchResult: Ref<Api.GetResponse<T>> = ref({
  total_count: 0,
  data: [],
})

async function handleSearch(val: string) {
  showSearchModal()
  startSearchLoading()
  try {
    const { onSubmit } = props

    if (typeof onSubmit === "function") {
      const data = await onSubmit(val)

      if (data) {
        searchResult.value = data
        emits("search:result", data)
      }
    }
    else {
      const { data, error } = await request<Api.GetResponse<Api.Search.SearchItem>>({
        url: "/search",
        params: { input: val },
      })

      if (data) {
        searchResult.value = data as Api.GetResponse<T>
        emits("search:result", data as Api.GetResponse<T>)
      }
    }
  }
  catch (e) {
    // message.error("Failed")
  }
  finally {
    setTimeout(() => stopSearchLoading(), 100)
  }
}

function restoreSearch() {
  searchResult.value = {
    total_count: 0,
    data: [],
  }
}
</script>

<style scoped lang="sass"></style>

<template>
  <div class="py-6">
    <div class="flex justify-between">
      <h2 class="mb-6 text-2xl text-gray-800 font-bold">
        {{ $t("page.hub.title") }}
      </h2>
      <n-button type="primary" quaternary>
        <template #icon>
          <n-icon size="16">
            <icon-ion-add-outline />
          </n-icon>
        </template>
        {{ $t("page.hub.uploadProtocol") }}
      </n-button>
    </div>

    <n-card class="mb-8">
      <div class="flex flex-nowrap justify-between gap-4">
        <search-input
          v-model:value="searchQuery"
          icon-position="right"
          :placeholder="$t('page.hub.searchPlaceholder')"
        />
        <n-popselect v-model:value="selectedCategory" :options="categories">
          <n-button icon-placement="right" quaternary class="h-9">
            <span class="mr-2 text-sm">{{ $t("common.category") }}:</span>
            <span class="text-sm font-semibold">{{ selectedCategoryLabel }}</span>
            <template #icon>
              <n-icon size="16">
                <icon-carbon-chevron-down />
              </n-icon>
            </template>
          </n-button>
        </n-popselect>

        <n-popselect v-model:value="sortBy" :options="sortOptions">
          <n-button icon-placement="right" quaternary class="h-9">
            <span class="mr-2 text-sm">{{ $t("common.sortBy") }}:</span>
            <span class="text-sm font-semibold">{{ selectedSortLabel }}</span>
            <template #icon>
              <n-icon size="16">
                <icon-carbon-chevron-down />
              </n-icon>
            </template>
          </n-button>
        </n-popselect>
      </div>
    </n-card>

    <div class="grid grid-cols-1 gap-6 lg:grid-cols-3 md:grid-cols-2">
      <protocol-card
        v-for="item in protocols"
        :key="item.protocol.id"
        :protocol="item.protocol"
        :project="item.project"
        :lab="item.lab"
        @click="navigateToDetail(item.protocol.id)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DropdownOption } from "naive-ui"
import SearchInput from "@/components/common/search-input.vue"
import ProtocolCard from "@/components/protocol/protocol-card.vue"
import { $t } from "@airalogy/shared/locales"
import { useRouter } from "vue-router"

const router = useRouter()
const searchQuery = ref("")
const sortBy = ref("newest")

const categories = computed<DropdownOption[]>(() => ([
  { label: $t("common.all"), value: "all", key: "all" },
  { label: $t("page.hub.category.biology"), value: "biology", key: "biology" },
  { label: $t("page.hub.category.chemistry"), value: "chemistry", key: "chemistry" },
  { label: $t("page.hub.category.physics"), value: "physics", key: "physics" },
]))

const sortOptions = computed<DropdownOption[]>(() => ([
  { label: $t("page.hub.sort.popularity"), value: "popularity", key: "popularity" },
  { label: $t("page.hub.sort.recentlyUpdated"), value: "recently_updated", key: "recently_updated" },
  { label: $t("page.hub.sort.bestMatch"), value: "best_match", key: "best_match" },
]))
const selectedCategory = ref<string>("")
const selectedCategoryLabel = computed(() => {
  const category = categories.value.find(c => c.value === selectedCategory.value)
  return category?.label || $t("common.category")
})

const selectedSortLabel = computed(() => {
  const option = sortOptions.value.find(opt => opt.value === sortBy.value)
  return option?.label || $t("common.sortBy")
})

const protocols = ref<{ protocol: Api.Hub.Protocol, project: Api.Project.MyProjectInfo, lab: Api.Lab.LabInfo }[]>()

function navigateToDetail(id: string) {
  router.push(`/protocols/${id}`)
}
</script>

<script setup lang="ts">
import type { DataTableColumns } from "naive-ui"
import { $t } from "@airalogy/shared/locales"
import { NButton, NCard, NDataTable, NPopconfirm, NSpace, NTabPane, NTabs } from "naive-ui"
import { h, ref } from "vue"

interface Protocol {
  id: string
  name: string
  status: string
  lastUpdated: string
  views: number
  downloads: number
}

const protocols = ref<Protocol[]>([
  {
    id: "1",
    name: $t("page.hub.dashboard.sampleProtocolName"),
    status: "published",
    lastUpdated: "2024-03-15",
    views: 1205,
    downloads: 367,
  },
])

function handleDelete(id: string) {
  protocols.value = protocols.value.filter(p => p.id !== id)
}

const columns = computed<DataTableColumns<Protocol>>(() => ([
  {
    title: $t("common.name"),
    key: "name",
  },
  {
    title: $t("common.status"),
    key: "status",
  },
  {
    title: $t("common.lastUpdated"),
    key: "lastUpdated",
  },
  {
    title: $t("common.views"),
    key: "views",
  },
  {
    title: $t("common.downloads"),
    key: "downloads",
  },
  {
    title: $t("common.actions"),
    key: "actions",
    render(row) {
      return h(NSpace, null, {
        default: () => [
          h(
            NButton,
            {
              size: "small",
              onClick: () => console.log("Edit", row.id),
            },
            { default: () => $t("common.edit") },
          ),
          h(
            NPopconfirm,
            {
              onPositiveClick: () => handleDelete(row.id),
            },
            {
              default: () => $t("common.confirmDelete"),
              trigger: () =>
                h(
                  NButton,
                  {
                    size: "small",
                    type: "error",
                  },
                  { default: () => $t("common.delete") },
                ),
            },
          ),
        ],
      })
    },
  },
]))
</script>

<template>
  <div>
    <h2 class="mb-6 text-2xl font-bold">
      {{ $t("page.hub.dashboard.title") }}
    </h2>
    <n-tabs type="segment" class="mb-6">
      <n-tab-pane name="protocols" :tab="$t('page.hub.dashboard.myProtocols')">
        <n-card>
          <template #header>
            <div class="flex items-center justify-between">
              <span class="font-medium">{{ $t("common.protocolsLabel") }}</span>
              <n-button type="primary" size="small">
                {{ $t("common.newProtocol") }}
              </n-button>
            </div>
          </template>
          <n-data-table :columns="columns" :data="protocols" :bordered="false" />
        </n-card>
      </n-tab-pane>
      <n-tab-pane name="analytics" :tab="$t('page.hub.dashboard.analytics')">
        <n-card>
          <p>{{ $t("page.hub.dashboard.analyticsPlaceholder") }}</p>
        </n-card>
      </n-tab-pane>
      <n-tab-pane name="settings" :tab="$t('page.hub.dashboard.settings')">
        <n-card>
          <p>{{ $t("page.hub.dashboard.settingsPlaceholder") }}</p>
        </n-card>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

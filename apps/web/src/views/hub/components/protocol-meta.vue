<template>
  <div class="border rounded-lg p-4 space-y-3">
    <h3 class="text-lg font-medium">
      {{ $t("page.protocol.info") }}
    </h3>
    <div class="space-y-2">
      <div class="flex justify-between">
        <span class="text-gray-600">{{ $t("common.created") }}</span>
        <span>{{ formatDate(item.created_at) }}</span>
      </div>
      <div class="flex justify-between">
        <span class="text-gray-600">{{ $t("common.updated") }}</span>
        <span>{{ formatDate(item.updated_at) }}</span>
      </div>
      <div class="flex justify-between">
        <span class="text-gray-600">{{ $t("common.version") }}</span>
        <span>{{ item.version }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { $t } from "@airalogy/shared/locales"
import { formatDate as formatDateBase } from "@airalogy/shared/utils"

interface Props {
  item: {
    created_at: string
    updated_at: string
    version: string
  }
}
defineProps<Props>()

function formatDate(date: string) {
  return formatDateBase(date, "date")
}
</script>

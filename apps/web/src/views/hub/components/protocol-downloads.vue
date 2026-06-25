<template>
  <div class="border rounded-lg p-4 space-y-3">
    <h3 class="text-lg font-medium">
      {{ $t("page.hub.downloadsStatsTitle") }}
    </h3>
    <div class="space-y-2">
      <div class="flex justify-between">
        <span class="text-gray-600">{{ $t("common.downloads") }}</span>
        <span class="font-medium">{{ downloadCount }}</span>
      </div>
      <div class="flex justify-between">
        <span class="text-gray-600">{{ $t("common.stars") }}</span>
        <span class="font-medium">{{ stars }}</span>
      </div>
      <div class="flex justify-between">
        <span class="text-gray-600">{{ $t("common.forks") }}</span>
        <span class="font-medium">{{ forks }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { $t } from "@airalogy/shared/locales"

interface Props {
  downloadCount: number
  stars: number
  forks: number
}

defineProps<Props>()
</script>

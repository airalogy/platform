<template>
  <n-card size="small" class="categories-card">
    <!-- Categories Section -->
    <div v-if="discipline.length" class="mb-6">
      <h3 class="mb-3 text-base font-medium">
        {{ $t("common.disciplines") }}
      </h3>
      <div class="flex flex-wrap gap-2">
        <n-tag
          v-for="category in discipline"
          :key="category"
          :bordered="false"
          size="small"
          :color="{ color: '#E8F3FF', textColor: '#1A79FF' }"
        >
          {{ category }}
        </n-tag>
      </div>
    </div>

    <!-- Tags Section -->
    <div v-if="keywords.length" :class="{ 'mb-6': !discipline.length }">
      <h3 class="mb-3 text-base font-medium">
        {{ $t("common.keywords") }}
      </h3>
      <div class="flex flex-wrap gap-2">
        <n-tag
          v-for="tag in keywords"
          :key="tag"
          :bordered="false"
          size="small"
          :color="{ color: '#F4F4F5', textColor: '#71717A' }"
        >
          {{ tag }}
        </n-tag>
      </div>
    </div>
  </n-card>
</template>

<script setup lang="ts">
import { $t } from "@airalogy/shared/locales"
import { NCard, NTag } from "naive-ui"

defineProps<{
  discipline: string[]
  keywords: string[]
}>()
</script>

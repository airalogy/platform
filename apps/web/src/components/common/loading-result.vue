<template>
  <template v-if="result?.ok">
    <n-empty v-if="isShowEmpty" :description="emptyText" />
    <slot v-else :value="result.value" :loading="loading" />
  </template>

  <n-result v-else-if="result && !result.ok" status="error" :title="loadErrorText" :description="result.error.message" />
</template>

<script setup lang="ts" generic="T extends unknown">
import { $t } from "@/locales"

export type Result<T> = { ok: true, value: T } | { ok: false, error: { message: string } }

const props = withDefaults(
  defineProps<{
    result?: Result<T> | null
    loading?: T[]
    showEmpty?: (value: T) => boolean
  }>(),
  {
    result: null,
    showEmpty: () => false,
  },
)

const isShowEmpty = computed(() => {
  const { showEmpty, result } = props
  if (result && result.ok) {
    return typeof showEmpty === "function" && showEmpty(result.value)
  }

  return false
})

const emptyText = computed(() => $t("common.emptyList"))
const loadErrorText = computed(() => $t("common.loadError"))
</script>

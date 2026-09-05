<template>
  <div ref="root" role="alert" tabindex="-1">
    <n-alert type="error" :title="title || $t('common.operationFailed')">
      {{ message || $t("common.inputPreserved") }}
      <p v-if="uncertain" class="mb-0 mt-2">{{ $t("common.checkBeforeRetry") }}</p>
    </n-alert>
  </div>
</template>

<script setup lang="ts">
import { $t } from "@airalogy/shared/locales"

defineProps<{ title?: string, message?: string, uncertain?: boolean }>()
const root = ref<HTMLElement | null>(null)
onMounted(async () => {
  await nextTick()
  root.value?.focus({ preventScroll: true })
  root.value?.scrollIntoView({ block: "nearest" })
})
</script>

<template>
  <div class="wh-full min-h-520px flex-vertical-center gap-24px overflow-hidden">
    <div class="flex text-3xl text-primary">
      {{ icon }}
    </div>
    <router-link to="/">
      <n-button type="primary">
        {{ $t("common.backToHome") }}
      </n-button>
    </router-link>
  </div>
</template>

<script lang="ts" setup>
import { $t } from "@airalogy/shared/locales"
import { computed } from "vue"

defineOptions({ name: "ExceptionBase" })

const props = defineProps<Props>()

type ExceptionType = "403" | "404" | "500"

interface Props {
  /**
   * Exception type
   *
   * - 403: no permission
   * - 404: not found
   * - 500: service error
   */
  type: ExceptionType
}

const iconMap: Record<ExceptionType, string> = {
  403: "no-permission",
  404: "not-found",
  500: "service-error",
}

const icon = computed(() => iconMap[props.type])
</script>

<style scoped></style>

<template>
  <div
    class="absolute inset-0 z-10 flex flex-col items-center justify-center rounded bg-[rgba(255,255,255,0.9)] p-6 text-black"
  >
    <n-icon size="64" class="mb-4">
      <time-outline />
    </n-icon>
    <h2 class="mb-2 text-3xl font-bold">
      {{ titleText }}
    </h2>
    <p class="mb-6 text-lg opacity-80">
      {{ descriptionText }}
    </p>
    <n-button type="primary" size="large" @click="handleButtonClick">
      {{ buttonTextValue }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { $t } from "@airalogy/shared/locales"
import TimeOutline from "~icons/ion/time-outline"

interface Props {
  title?: string
  description?: string
  buttonText?: string
}

const props = defineProps<Props>()

const emit = defineEmits(["button:click"])
const titleText = computed(() => props.title || $t("page.login.formOverlay.title"))
const descriptionText = computed(() => props.description || $t("page.login.formOverlay.description"))
const buttonTextValue = computed(() => props.buttonText || $t("page.login.formOverlay.button"))

function handleButtonClick() {
  emit("button:click")
}
</script>

<style scoped>
</style>

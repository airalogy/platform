<template>
  <div class="h-full flex flex-col items-center px-4">
    <div class="mb-4 flex items-center gap-3">
      <n-icon :size="40" class="shrink-0 text-primary">
        <icon-shared-airalogy-logo />
      </n-icon>
      <h2 class="text-left text-xl font-medium">
        {{ $t("chat.airaIntroTitle") }}
      </h2>
    </div>

    <div class="space-y-4">
      <div class="text-left">
        <p class="text-sm text-neutral-600">
          {{ $t("chat.airaIntroSubtitle") }}
        </p>
      </div>

      <div class="grid grid-cols-1 gap-1.5">
        <n-button
          v-for="(example, index) in examples"
          :key="index"
          text
          size="small"
          class="group justify-start transition-colors duration-200 hover:bg-primary/5 !text-left"
          @click="() => onExampleClick(example)"
        >
          <template #icon>
            <n-icon class="text-primary/70 transition-colors group-hover:text-primary">
              <message-circle-icon />
            </n-icon>
          </template>
          <span class="text-neutral-600 group-hover:text-primary">{{ typeof example === 'string' ? example : example.text }}</span>
        </n-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import MessageCircleIcon from "~icons/lucide/message-circle"
import { $t } from "@airalogy/shared/locales"
import { NButton, NIcon } from "naive-ui"

defineProps<{
  examples: Chat.Example[]
}>()

const emit = defineEmits<{
  (e: "exampleClick", example: Chat.Example): void
}>()

function onExampleClick(example: Chat.Example) {
  emit("exampleClick", example)
}
</script>

<style lang="sass" scoped>
.n-button
  &.n-button--text-type
    padding: 0.375rem 0.75rem
    border-radius: 0.5rem

    .n-button__icon
      margin-right: 0.5rem
      font-size: 1rem

    &:hover
      background-color: var(--n-color-hover)
</style>

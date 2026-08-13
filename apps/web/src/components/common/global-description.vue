<template>
  <n-card v-if="Boolean(props.description)" bordered class="mt-5 w-full" content-class="!text-4">
    <div ref="descriptionContainerRef" class="relative">
      <div
        ref="descriptionMeasureRef"
        aria-hidden="true"
        class="description-measure line-clamp-3"
      >
        {{ description }}
      </div>
    </div>
    <n-tooltip :disabled="!showTooltip" trigger="hover" placement="top-start" :show-arrow="false">
      <template #trigger>
        <div data-testid="global-description-text" :class="{ 'line-clamp-3': !showFullContent }">
          {{ description }}
        </div>
      </template>
      <div class="desc-tooltip">
        {{ description }}
      </div>
    </n-tooltip>
    <n-button v-if="showButton" data-testid="global-description-toggle" inline @click="toggle">
      {{ showFullContent ? $t("common.showLess") : $t("common.readMore") }}
    </n-button>
  </n-card>
</template>

<script setup lang="ts">
import { $t } from "@airalogy/shared/locales"

interface IProps {
  description: string
}

const props = defineProps<IProps>()

const descriptionContainerRef = ref<HTMLElement | null>(null)
const descriptionMeasureRef = ref<HTMLElement | null>(null)
const showButton = ref(false)
const showFullContent = ref(false)

function updateOverflowState() {
  const element = descriptionMeasureRef.value
  showButton.value = Boolean(element && element.scrollHeight - element.clientHeight > 1)
}

function toggle() {
  showFullContent.value = !showFullContent.value
}

useResizeObserver(descriptionContainerRef, updateOverflowState)

watch(
  () => props.description,
  async () => {
    showFullContent.value = false
    await nextTick()
    updateOverflowState()
  },
  { immediate: true },
)

const showTooltip = computed(() => showButton.value && !showFullContent.value)
</script>

<style scoped>
.description-measure {
  position: absolute;
  width: 100%;
  visibility: hidden;
  pointer-events: none;
}

.desc-tooltip {
  max-width: 420px;
  white-space: normal;
  word-break: break-word;
}
</style>

<template>
  <n-card v-if="Boolean(props.description)" bordered class="mt-5 w-full" content-class="!text-4">
    <n-tooltip v-if="showTooltip" trigger="hover" placement="top-start" :show-arrow="false">
      <template #trigger>
        <div :class="{ 'line-clamp-3': !showFullContent }">
          {{ description }}
        </div>
      </template>
      <div class="desc-tooltip">
        {{ description }}
      </div>
    </n-tooltip>
    <div v-else>
      {{ description }}
    </div>
    <n-button v-if="showButton" inline @click="toggle">
      {{ showFullContent ? $t("common.showLess") : $t("common.readMore") }}
    </n-button>
  </n-card>
</template>

<script setup lang="ts">
import { useBoolean } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"

interface IProps {
  description: string
}

const props = defineProps<IProps>()

const showButton = computed(() => props.description.length > 200)

const { bool: showFullContent, toggle } = useBoolean(!showButton.value)

const showTooltip = computed(() => !showFullContent.value)
</script>

<style scoped>
.desc-tooltip {
  max-width: 420px;
  white-space: normal;
  word-break: break-word;
}
</style>

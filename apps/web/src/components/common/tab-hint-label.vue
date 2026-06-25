<template>
  <span class="tab-hint-label">
    <span class="tab-hint-label__text">{{ props.label }}</span>
    <n-tooltip trigger="hover" placement="top" :show-arrow="false" :show-after="0">
      <template #trigger>
        <span class="tab-hint-label__icon" :aria-label="props.hint">
          <n-icon size="14">
            <icon-tabler-info-circle />
          </n-icon>
        </span>
      </template>
      <span class="tab-hint-label__tooltip">{{ props.hint }}</span>
    </n-tooltip>
  </span>
</template>

<script setup lang="ts">
import IconTablerInfoCircle from "~icons/tabler/info-circle"
import { NIcon, NTooltip } from "naive-ui"

interface Props {
  label: string
  hint: string
}

const props = defineProps<Props>()
</script>

<style scoped lang="sass">
.tab-hint-label
  display: inline-flex
  align-items: center
  gap: 4px
  white-space: nowrap

.tab-hint-label__icon
  display: inline-flex
  align-items: center
  color: rgb(156 163 175)
  cursor: help

.tab-hint-label__icon:hover
  color: rgb(75 85 99)

.tab-hint-label__tooltip
  white-space: nowrap
</style>

<template>
  <n-tooltip>
    <template #trigger>
      <span :class="props.triggerClass">
        <span class="mr-1" :class="props.labelClass">{{ props.label }}</span>
        <n-time :time="dayjs(props.time).toDate()" type="relative" :class="props.timeClass" />
      </span>
    </template>
    <span>
      {{ formatDate(props.time, "date-time") }}
    </span>
  </n-tooltip>
</template>

<script lang="ts" setup>
import { formatDate } from "@airalogy/shared/utils"
import dayjs from "dayjs"

interface Props {
  time: string
  label: string
  triggerClass?: string
  labelClass?: string
  timeClass?: string
}

const props = withDefaults(defineProps<Props>(), {
  triggerClass: "text-sm",
  labelClass: "text-text-secondary",
  timeClass: "",
})
</script>

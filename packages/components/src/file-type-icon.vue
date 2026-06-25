<template>
  <div class="relative size-fit">
    <n-icon :size="size" :class="colorClass" v-bind="$attrs">
      <component :is="icon" />
    </n-icon>
    <slot />
  </div>
</template>

<script setup lang="ts">
import { getFileCategoryIcon, type IFileType } from "@airalogy/shared/utils"

interface Props {
  type: IFileType
  size?: number | string
  color?: string
  showColor?: boolean
}

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<Props>(), {
  size: 16,
  color: "",
  showColor: false,
})

const colorMap: Partial<Record<IFileType, string>> = {
  image: "text-blue-500",
  audio: "text-green-500",
  file: "text-gray-500",
  video: "text-red-500",
  pdf: "text-purple-500",
  word: "text-yellow-500",
  excel: "text-orange-500",
  ppt: "text-pink-500",
  zip: "text-gray-500",
  exe: "text-gray-500",
  csv: "text-gray-500",
  unknown: "text-gray-400",
  code: "text-gray-400",
  text: "text-gray-400",
}
const colorClass = computed(() => {
  if (props.color)
    return props.color

  if (!props.showColor)
    return ""

  return colorMap[props.type]
})
const icon = computed(() => {
  return getFileCategoryIcon(props.type, false, true)
})
</script>

<style lang="sass" scoped>
:deep(.thin-stroke g)
  stroke-width: 1.25
</style>

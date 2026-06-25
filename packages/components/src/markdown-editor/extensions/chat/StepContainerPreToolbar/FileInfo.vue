<template>
  <tooltip-button
    :class="props.clickable && 'cursor-pointer hover:underline'" class="flex flex-row select-none items-center gap-0.5"
    :tooltip="props.filepath"
    quaternary
    :icon="fileIcon"
  >
    <span className="line-clamp-1 break-all">
      {{ basename }}
      {{ props.range && ` ${props.range}` }}
    </span>
  </tooltip-button>
</template>

<script lang="ts" setup>
import tooltipButton from "@airalogy/components/tooltip-button.vue"
import { getFileSpecificIcon, getUriPathBasename } from "@airalogy/shared/utils"

export interface FileInfoProps {
  filepath: string
  clickable?: boolean
  range?: string
}

const props = defineProps<FileInfoProps>()
const basename = computed(() => getUriPathBasename(props.filepath))
const fileIcon = computed(() => getFileSpecificIcon(basename.value))
</script>

<template>
  <div>
    <command-button
      :command="() => toggleFullscreen(!isFullscreen)"
      :enable-tooltip="enableTooltip"
      :tooltip="buttonTooltip"
      :icon="isFullscreen ? ArrowsJoin : ArrowsDiagonal"
      :is-active="isFullscreen"
    />
  </div>
</template>

<script setup lang="ts">
import type { Editor } from "@tiptap/core"
import { $t } from "@airalogy/shared/locales"
import ArrowsDiagonal from "~icons/tabler/arrows-diagonal"
import ArrowsJoin from "~icons/tabler/arrows-join"

import CommandButton from "../menu-bar-item.vue"

defineOptions({ name: "FullscreenIcon" })

const props = defineProps<IProps>()

interface IProps {
  editor: Editor
}

const enableTooltip = inject("enableTooltip", true)
const isFullscreen = inject("isFullscreen", false)
const toggleFullscreen = inject("toggleFullscreen") as (state: boolean) => void

const buttonTooltip = computed(() => {
  return isFullscreen
    ? $t("editor.extensions.Fullscreen.tooltip.exit_fullscreen")
    : $t("editor.extensions.Fullscreen.tooltip.fullscreen")
})
</script>

<template>
  <menu-bar-item
    :command="openLink"
    :enable-tooltip="enableTooltip"
    :tooltip="$t('editor.extensions.Link.open.tooltip')"
    :icon="ExternalLink"
  />
</template>

<script setup lang="ts">
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"

import ExternalLink from "~icons/tabler/external-link"

interface IProps {
  url?: string
}

const props = defineProps<IProps>()
const enableTooltip = inject("enableTooltip", true)
function openLink() {
  const { url } = props

  if (!url) {
    return
  }

  // new window
  const newTab = window.open()
  if (newTab) {
    newTab.opener = null
    newTab.location.href = url
  }
}
</script>

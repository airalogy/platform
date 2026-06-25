<template>
  <menu-bar-item
    :command="() => editor.commands.unsetLink()"
    :enable-tooltip="enableTooltip"
    :tooltip="$t('editor.extensions.Link.unlink.tooltip')"
    :icon="Unlink"
  />
</template>

<script setup lang="ts">
import type { Editor } from "@tiptap/vue-3"

import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"

import { $t } from "@airalogy/shared/locales"
import Unlink from "~icons/tabler/unlink"

interface IProps {
  editor: Editor
}

const props = defineProps<IProps>()

const enableTooltip = inject("enableTooltip", true)
</script>

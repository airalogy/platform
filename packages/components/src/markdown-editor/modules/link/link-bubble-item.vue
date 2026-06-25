<template>
  <div class="link-bubble-menu">
    <slot name="prepend" />

    <open-link-item :url="linkAttrs.href" />
    <edit-link-item :editor="editor" :init-link-attrs="linkAttrs" />
    <unset-link-item :editor="editor" />
  </div>
</template>

<script setup lang="ts">
import type { Editor } from "@tiptap/vue-3"

import EditLinkItem from "./edit-link-item.vue"
import OpenLinkItem from "./open-link-item.vue"
import UnsetLinkItem from "./unset-link-item.vue"

defineOptions({ name: "LinkBubbleMenu" })

const props = defineProps<IProps>()

interface IProps {
  editor: Editor
}

const linkAttrs = computed<any>(() => {
  return props.editor.getAttributes("link")
})
</script>

<style lang="sass">
.link-bubble-menu
  display: flex
</style>

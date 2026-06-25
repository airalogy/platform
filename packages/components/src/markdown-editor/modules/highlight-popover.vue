<template>
  <menu-bar-item
    :enable-tooltip="enableTooltip"
    :tooltip="$t('editor.extensions.TextHighlight.tooltip')"
    :icon="Highlight"
  >
    <template #default="{ isActive, handleClick, themeOverrides, icon }">
      <n-popover ref="popoverRef" placement="bottom" trigger="click" content-class="tiptap-popover">
        <div class="color-set">
          <div v-for="color in colorSet" :key="color" class="color__wrapper">
            <div
              :style="{ 'background-color': color }"
              :class="{ 'color--selected': selectedColor === color }"
              class="color"
              @mousedown.prevent
              @click.stop="confirmColor(color)"
            />
          </div>

          <div class="color__wrapper">
            <div class="color color--remove" @mousedown.prevent @click.stop="confirmColor()" />
          </div>
        </div>

        <template #trigger>
          <n-button
            quaternary
            circle
            :type="isActive ? 'primary' : 'default'"
            size="medium"
            :theme-overrides="themeOverrides"
            @click="handleClick"
          >
            <n-icon v-if="icon" :component="icon" />
          </n-button>
        </template>
      </n-popover>
    </template>
  </menu-bar-item>
</template>

<script setup lang="ts">
import type { Editor } from "@tiptap/vue-3"
import type { PopoverInst } from "naive-ui"
import { getMarkAttributes } from "@tiptap/vue-3"

import Highlight from "~icons/tabler/highlight"

import MenuBarItem from "../menu-bar-item.vue"

defineOptions({ name: "HighlightPopover" })

const props = defineProps<IProps>()

interface IProps {
  editor: Editor
}

const enableTooltip = inject("enableTooltip", true)

const popoverRef = ref<PopoverInst | null>(null)

function confirmColor(color?: string) {
  if (color) {
    props.editor.commands.setHighlight({ color })
  }
  else {
    props.editor.commands.unsetHighlight()
  }

  const inst = unref(popoverRef)

  if (inst) {
    inst.setShow(false)
  }
}

const selectedColor = computed<string>(() => {
  return getMarkAttributes(props.editor.state, "highlight").color || ""
})

const colorSet = computed((): string[] => {
  const { editor } = props
  const colorOptions = editor.extensionManager.extensions.find(e => e.name === "highlight")?.options

  if (colorOptions) {
    return colorOptions.colors
  }

  return []
})
</script>

<style scoped lang="sass">
@use "../styles/color" as *
</style>

<template>
  <menu-bar-item
    :enable-tooltip="enableTooltip"
    :tooltip="$t('editor.extensions.TextColor.tooltip')"
    :icon="ColorPicker"
    :readonly="isCodeViewMode"
  >
    <template #default="{ isActive, handleClick, themeOverrides, icon }">
      <n-popover
        ref="popoverRef"
        :disabled="isCodeViewMode"
        placement="bottom"
        trigger="click"
        content-class="tiptap-popper"
      >
        <div class="color-set">
          <div v-for="color in colorSet" :key="color" class="color__wrapper">
            <div
              :style="{
                'background-color': color,
              }"
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

        <div class="color-hex">
          <n-input
            v-model="colorText"
            placeholder="HEX"
            autofocus
            maxlength="7"
            size="small"
            class="color-hex__input"
          />

          <n-button
            text
            type="primary"
            size="small"
            class="color-hex__button"
            @click="confirmColor(colorText)"
          >
            Confirm
          </n-button>
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

<script lang="ts" setup>
import type { PopoverInst } from "naive-ui/es"
import { type Editor, getMarkAttributes } from "@tiptap/vue-3"
import ColorPicker from "~icons/tabler/color-picker"
import { computed, inject, ref, unref, watch } from "vue"

import MenuBarItem from "../menu-bar-item.vue"

defineOptions({ name: "ColorPopover" })

const props = defineProps<IProps>()
interface IProps {
  editor: Editor
}
const enableTooltip = inject("enableTooltip", true)
const isCodeViewMode = inject("isCodeViewMode", false)

const popoverRef = ref<PopoverInst | null>(null)
const colorText = ref("")

function confirmColor(color?: string) {
  if (color) {
    props.editor.commands.setColor(color)
  }
  else {
    props.editor.commands.unsetColor()
  }

  const inst = unref(popoverRef)

  if (inst) {
    inst.setShow(false)
  }
}

const selectedColor = computed<string>(() => {
  return (getMarkAttributes(props.editor.state, "textStyle").color as string) || ""
})

watch(selectedColor, (color) => {
  colorText.value = color
})

const colorSet = computed(() => {
  const colorOptions = props.editor.extensionManager.extensions.find(
    e => e.name === "color",
  )!.options

  return colorOptions.colors as string[]
})
</script>

<style scoped lang="sass">
@use "../styles/color" as *
</style>

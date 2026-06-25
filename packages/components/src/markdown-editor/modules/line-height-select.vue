<template>
  <menu-bar-item
    :enable-tooltip="enableTooltip"
    :tooltip="$t('editor.extensions.LineHeight.tooltip')"
    :disabled="props.disabled"
  >
    <n-select
      :options="options"
      :render-label="renderSelectLabel"
      :value="activeLineHeight"
      size="small"
      placeholder="Line Height"
      class="editor__select w-25"
      :disabled="props.disabled"
      @update:value="handleSelect"
    />
  </menu-bar-item>
</template>

<script setup lang="tsx">
import type { Editor } from "@tiptap/core"
import type { SelectOption } from "naive-ui"
import type { RenderLabel } from "naive-ui/es/_internal/select-menu/src/interface"

import { $t } from "@airalogy/shared/locales"
import MenuBarItem from "../menu-bar-item.vue"
import { isLineHeightActive } from "../utils/line-height"

interface IProps {
  editor: Editor
  disabled?: boolean
}

defineOptions({ name: "FontSizeSelect" })

const props = defineProps<IProps>()

const enableTooltip = inject("enableTooltip", true)

const lineHeights = computed((): string[] => {
  const { editor } = props

  if (!editor) {
    return []
  }

  const { options } = editor.extensionManager.extensions.find(e => e.name === "lineHeight") || {}

  if (options) {
    return options.lineHeights
  }

  return []
})

const activeLineHeight = computed(() => {
  return lineHeights.value.find(val => isLineHeightActive(props.editor.state, val))
})

const options = computed((): SelectOption[] => {
  return lineHeights.value.map(name => ({
    label: name,
    value: name,
  }))
})

const renderSelectLabel: RenderLabel = (option) => {
  const { label, key } = option

  if (!key) {
    return <span>{label}</span>
  }

  const className = {
    "tiptap-dropdown-menu__item--active": key === activeLineHeight.value,
    "tiptap-dropdown-menu__item": true,
  }

  return (
    <span data-item-type="font-size" class={className}>
      {label}
    </span>
  )
}

function handleSelect(lineHeight: string) {
  const { editor } = props
  editor.chain().focus().setLineHeight(lineHeight).run()
}
</script>

<style scoped lang="sass">
.editor__select
  :deep(.n-base-selection)
    --n-height: 32px!important
</style>

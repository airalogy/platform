<template>
  <menu-bar-item
    :enable-tooltip="enableTooltip"
    :tooltip="$t('editor.extensions.FontFamily.tooltip')"
    :disabled="props.disabled"
  >
    <n-select
      :options="options"
      :render-label="renderDropdownLabel"
      :value="activeFontFamily"
      size="small"
      placeholder="Default Font"
      class="editor__select w-30"
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
import { getMarkAttributes } from "@tiptap/core"

import MenuBarItem from "../menu-bar-item.vue"

interface IProps {
  editor: Editor
  disabled?: boolean
}

defineOptions({ name: "FontFamilySelect" })

const props = defineProps<IProps>()

const enableTooltip = inject("enableTooltip", true)

const fontFamilies = computed((): Record<string, string> | null => {
  const { editor } = props

  if (!editor) {
    return null
  }

  const { options } = editor.extensionManager.extensions.find(e => e.name === "fontFamily") || {}

  if (options && options.fontFamilyMap) {
    return options.fontFamilyMap
  }

  return null
})

const activeFontFamily = computed(() => {
  return getMarkAttributes(props.editor.state, "textStyle").fontFamily
})

const options = computed((): SelectOption[] => {
  if (!fontFamilies.value) {
    return []
  }

  return [
    { label: "Default", value: undefined },
    ...Object.entries(fontFamilies.value).map(([value, label]) => ({
      label,
      value,
    })),
  ]
})

const renderDropdownLabel: RenderLabel = (option) => {
  const { label, key } = option

  if (!key) {
    return <span>{label}</span>
  }

  const className = {
    "tiptap-dropdown-menu__item--active": key === activeFontFamily.value,
    "tiptap-dropdown-menu__item": true,
  }

  return (
    <span data-item-type="font-family" class={className}>
      {label}
    </span>
  )
}

function handleSelect(value: string) {
  const { editor } = props
  const chain = editor.chain().focus()
  if (value === activeFontFamily.value) {
    chain.unsetFontFamily()
  }
  else {
    chain.setFontFamily(value)
  }

  chain.run()
}
</script>

<style scoped lang="sass">
.editor__select
  :deep(.n-base-selection)
    --n-height: 32px!important
</style>

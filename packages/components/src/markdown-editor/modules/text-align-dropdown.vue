<template>
  <n-dropdown
    placement="bottom"
    trigger="click"
    :options="options"
    :render-label="renderDropdownLabel"
    :render-icon="renderDropdownIcon"
    :on-select="handleSelect"
  >
    <menu-bar-item
      :enable-tooltip="enableTooltip"
      :is-active="editor.isActive('horizontal-rule')"
      :tooltip="$t('editor.extensions.TextAlign.tooltip')"
      :icon="AlignLeft"
    />
  </n-dropdown>
</template>

<script setup lang="tsx">
import type { Editor } from "@tiptap/core"

import type { DropdownOption } from "naive-ui"
import type { RenderIcon, RenderLabel } from "naive-ui/es/dropdown/src/interface"
import { $t } from "@airalogy/shared/locales"
import AlignCenter from "~icons/tabler/align-center"

import AlignJustified from "~icons/tabler/align-justified"
import AlignLeft from "~icons/tabler/align-left"
import AlignRight from "~icons/tabler/align-right"

import MenuBarItem from "../menu-bar-item.vue"

type IAlignment = "left" | "center" | "right" | "justify"

interface IProps {
  editor: Editor
  alignments?: IAlignment[]
}

defineOptions({ name: "TextAlignDropdown" })

const props = withDefaults(defineProps<IProps>(), {
  alignments: () => ["left", "center", "right", "justify"],
})

type CustomDropDownOption = DropdownOption & {
  isActive?: () => boolean
  key: string
}

const enableTooltip = inject("enableTooltip", true)
const iconRecord = {
  left: AlignLeft,
  center: AlignCenter,
  right: AlignRight,
  justify: AlignJustified,
} as Record<CustomDropDownOption["key"], Component>

const options = computed((): DropdownOption[] => {
  const { editor } = props

  return props.alignments.map(alignment => ({
    label: $t(`editor.extensions.TextAlign.buttons.align_${alignment}.tooltip` as any),
    key: alignment,
    isActive: editor.isActive.bind(null, { textAlign: alignment }),
  }))
})

const renderDropdownLabel: RenderLabel = (option) => {
  const { label, key, isActive } = option as CustomDropDownOption

  if (!key) {
    return <span>{label}</span>
  }

  const className = {
    "tiptap-dropdown-menu__item--active": typeof isActive === "function" && isActive(),
  }

  return (
    <span data-item-type="text-align" v-bind:class={className} class="tiptap-dropdown-menu__item">
      {label}
    </span>
  )
}

const renderDropdownIcon: RenderIcon = (option) => {
  const { key } = option as CustomDropDownOption
  return h(iconRecord[key])
}

function handleSelect(alignment: IAlignment) {
  const { editor } = props
  const isActive = editor.isActive({ textAlign: alignment })

  if (isActive) {
    editor.commands.unsetTextAlign()
  }
  else {
    editor.commands.setTextAlign(alignment)
  }
}
</script>

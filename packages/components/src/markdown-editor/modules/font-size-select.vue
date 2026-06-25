<template>
  <menu-bar-item
    :enable-tooltip="enableTooltip"
    :is-active="editor.isActive('textStyle')"
    :tooltip="$t('editor.extensions.FontSize.tooltip')"
    :disabled="props.disabled"
  >
    <n-select
      :options="options"
      :render-label="renderLabel"
      :render-tag="renderTag"
      :value="activeFontSize"
      size="small"
      placeholder="Size"
      class="font-size__select"
      :class="[
        activeFontSize === 'default' ? 'font-size__select--normal' : 'font-size__select--active',
      ]"
      :consistent-menu-width="false"
      :theme-overrides="{
        peers: {
          InternalSelection: {
            heightMedium: '32px',
          },
        },
      }"
      :disabled="props.disabled"
      @update:value="handleSelect"
    />
  </menu-bar-item>
</template>

<script setup lang="tsx">
import type { Editor } from "@tiptap/core"
import type { SelectOption } from "naive-ui"
import { $t } from "@airalogy/shared/locales"
import { getMarkAttributes } from "@tiptap/core"
import MenuBarItem from "../menu-bar-item.vue"

interface Props {
  editor: Editor
  disabled?: boolean
}

defineOptions({ name: "FontSizeSelect" })

const props = defineProps<Props>()
const enableTooltip = inject("enableTooltip", true)

const fontSizes = computed((): string[] => {
  const { editor } = props
  if (!editor)
    return []

  const { options } = editor.extensionManager.extensions.find(e => e.name === "fontSize") || {}
  return options?.fontSizes || []
})

const activeFontSize = computed(() =>
  getMarkAttributes(props.editor.state, "textStyle")?.fontSize || "default",
)

const options = computed((): SelectOption[] => {
  if (!fontSizes.value)
    return []

  return [
    {
      label: "Default",
      value: "default",
      isActive: () => activeFontSize.value === "default",
    },
    ...fontSizes.value.map(size => ({
      label: size,
      value: size,
      isActive: () => activeFontSize.value === size,
    })),
  ]
})

function renderLabel(option: SelectOption) {
  const { label, value } = option

  const optionLabel = value === "default" ? "Default" : `${label}px`

  return (
    <div class="w-fit flex items-center gap-2 py-1">
      <span style={{ fontSize: typeof value === "number" ? `${value}px` : "inherit" }}>
        {optionLabel}
      </span>
    </div>
  )
}

function renderTag() {
  if (activeFontSize.value === "default") {
    return (
      <n-icon size="18" class="mr-1 mt-[7px]">
        <icon-bx-font-size />
      </n-icon>
    )
  }

  return (
    <span class="w-12">
      {activeFontSize.value}
      px
    </span>
  )
}

function handleSelect(value: string) {
  const { editor } = props
  const chain = editor.chain().focus()

  if (value === "default" || value === activeFontSize.value) {
    chain.unsetFontSize()
  }
  else {
    chain.setFontSize(value)
  }

  chain.run()
}
</script>

<style scoped lang="sass">
.font-size__select
  &--normal
    :deep(.n-base-selection__border)
      border: none!important
    :deep(.n-base-selection-label)
      background-color: transparent!important

  &--active
    min-width: 4rem
    width: fit-content
</style>

<template>
  <menu-bar-item
    :enable-tooltip="enableTooltip"
    :is-active="editor.isActive('heading')"
    :tooltip="$t('editor.extensions.Heading.tooltip')"
    :disabled="disabled"
  >
    <n-select
      :options="options"
      :render-label="renderLabel"
      :render-tag="renderTag"
      :value="activeHeading"
      class="heading__select"
      :class="[
        activeHeading === 0 ? 'heading__select--normal' : 'heading__select--active',
      ]"
      :consistent-menu-width="false"
      :theme-overrides="{
        peers: {
          InternalSelection: {
            heightMedium: '32px',
          },
        },
      }"
      :disabled="disabled"
      @update:value="handleSelect"
    />
  </menu-bar-item>
</template>

<script setup lang="tsx">
import type { Editor } from "@tiptap/core"
import type { Level } from "@tiptap/extension-heading"
import type { DropdownOption } from "naive-ui"
import type { RenderLabel } from "naive-ui/es/dropdown/src/interface"
import { $t } from "@airalogy/shared/locales"

import Heading from "~icons/ci/heading"
import H1 from "~icons/ci/heading-h1"
import H2 from "~icons/ci/heading-h2"
import H3 from "~icons/ci/heading-h3"
import H4 from "~icons/ci/heading-h4"
import H5 from "~icons/ci/heading-h5"
import H6 from "~icons/ci/heading-h6"

import { NSelect } from "naive-ui"
import MenuBarItem from "../menu-bar-item.vue"

defineOptions({ name: "HeadingSelect" })
const props = withDefaults(defineProps<Props>(), {
  levels: () => [1, 2, 3, 4],
})
const headingIcons = {
  0: Heading,
  1: H1,
  2: H2,
  3: H3,
  4: H4,
  5: H5,
  6: H6,
}
interface Props {
  editor: Editor
  levels: Level[]
  disabled?: boolean
}

const enableTooltip = inject("enableTooltip", true)

const headingExamples = {
  0: "Normal",
  1: "Heading 1",
  2: "Heading 2",
  3: "Heading 3",
  4: "Heading 4",
  5: "Heading 5",
  6: "Heading 6",
} as const

const headingStyles = {
  0: "text-base",
  1: "text-2xl font-bold",
  2: "text-xl font-bold",
  3: "text-lg font-bold",
  4: "text-base font-bold",
  5: "text-sm font-bold",
  6: "text-xs font-bold",
} as const

const activeHeading = computed(() => {
  const { levels, editor } = props
  return levels.find((level: number) => editor.isActive("heading", { level })) || 0
})

const options = computed((): DropdownOption[] => {
  const { editor, levels } = props

  return [
    {
      label: headingExamples[0],
      value: 0,
      isActive: editor.isActive.bind(null, "paragraph"),
    },
    ...levels.map(level => ({
      label: headingExamples[level],
      value: level,
      isActive: editor.isActive.bind(null, ["heading", { level }]),
    })),
  ]
})

const renderLabel: RenderLabel = (option) => {
  const { label, value } = option

  if (typeof value === "undefined" || value === null) {
    return <span>{label}</span>
  }

  return (
    <div class="w-fit flex items-center gap-2 py-1">
      <span class={`${headingStyles[value as keyof typeof headingStyles]} truncate`}>
        {headingExamples[value as keyof typeof headingExamples]}
      </span>
    </div>
  )
}

function renderTag() {
  const HeadingIcon = activeHeading.value === 0
    ? Heading
    : headingIcons[activeHeading.value as keyof typeof headingIcons] ?? Heading

  return (
    <n-icon size="16" class="mr-1 mt-[0.25em] font-bold">
      <HeadingIcon />
    </n-icon>
  )
}

function handleSelect(level: Level) {
  if (level > 0) {
    props.editor.commands.toggleHeading({ level })
  }
  else {
    props.editor.commands.setParagraph()
  }
}
</script>

<style scoped lang="sass">
@use "../styles/variable.sass" as *

.heading__select
  &--normal
    :deep(.n-base-selection__border)
      border: none!important
    :deep(.n-base-selection-label)
      background-color: transparent!important
</style>

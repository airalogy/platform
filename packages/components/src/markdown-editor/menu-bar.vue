<template>
  <div class="menu-bar__wrapper flex flex-wrap items-center gap-y-2" @click="isEditorBubbleActive = true">
    <template
      v-for="(section, sectionIndex) in sections"
      :key="`menu-section-${sectionIndex}`"
    >
      <menu-section :editor="editor" :items="section.items" :disabled="props.disabled" />
      <n-divider
        v-if="sectionIndex !== sections.length - 1"
        vertical
        class="!mx-0"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import type { Editor } from "@tiptap/vue-3"
import type { IndentAlignment } from "./extensions/indent"

import type { MenuSectionConfig } from "./types/editor"
import MenuSection from "./menu-section.vue"
import { executeCompactAction, getMenuSectionIcon } from "./utils/compact-actions"

interface Props {
  editor: Editor
  preset?: "all" | "compact" | "simple"
  extraActions?: MenuSectionConfig[]
  disabled?: boolean
}

const props = defineProps<Props>()

const isEditorBubbleActive = injectLocal("isEditorBubbleActive", ref(false))

// const sectionRecords = {
//   advanced: ["rawContent", "compactMenu"],
//   history: ["undo", "redo", "history"],
//   insert: ["airalogyImage", "horizontalRule", "codeBlock", "table", "link"],
//   format: ["heading"],
//   alignment: ["textAlign"],
//   indent: ["outdent", "indent"],
//   list: ["bulletList", "orderedList", "taskList"],
// } as const

// export type SectionKey = keyof typeof sectionRecords

// export type ExtensionRecord = (typeof sectionRecords)[SectionKey]

// Computed properties
const basePresetSections: MenuSectionConfig[] = [
  { name: "advanced", items: ["rawContent", "compactMenu"] },
]

const compactPresetSections: MenuSectionConfig[] = [
  { name: "history", items: ["history"] },
  {
    name: "insert",
    items: [
      "airalogyImage",
      "table",
      {
        name: "insert-group",
        icon: getMenuSectionIcon("insert"),
        tooltip: "Insert",
        items: [
          { name: "horizontalRule", label: "Horizontal Rule" },
          { name: "codeBlock", label: "Code Block" },
          { name: "link", label: "Link" },
        ],
      },
    ],
  },
  { name: "format", items: ["heading"] },
  // {
  //   name: "alignment",
  //   items: [
  //     {
  //       name: "textAlign",
  //       icon: getMenuSectionIcon("alignment"),
  //       items: ["textAlign"],
  //       tooltip: "Text Alignment",
  //       renderLabel: (t, alignment: TextAlignAlignment) => t(`editor.extensions.TextAlign.buttons.align_${alignment}.tooltip`),
  //     },
  //   ],
  // },
  {
    name: "text",
    items: [
      "fontSize",
      {
        name: "text-group",
        icon: getMenuSectionIcon("text"),
        tooltip: "Text Formatting",
        items: [
          { name: "strike", label: "Strike" },
          { name: "underline", label: "Underline" },
          { name: "bold", label: "Bold" },
          { name: "italic", label: "Italic" },
        ],
      },
    ],
  },
  {
    name: "indent",
    items: [
      {
        name: "indent",
        icon: getMenuSectionIcon("indent"),
        items: ["indent"],
        tooltip: "Indentation",
        renderLabel: (t, indentType: IndentAlignment) => indentType === "indent" ? "Increase Indentation" : "Decrease Indentation",
      },
    ],
    tooltip: "Indentation",
    icon: getMenuSectionIcon("indent"),
  },
  {
    name: "list",
    items: [
      { name: "bulletList", label: "Bullet List" },
      { name: "orderedList", label: "Ordered List" },
      { name: "taskList", label: "Task List" },
    ],
    tooltip: "List",
    icon: getMenuSectionIcon("list"),
  },
]

const simplePresetSections: MenuSectionConfig[] = [
  {
    name: "insert",
    items: [
      "airalogyImage",
      {
        name: "insert-group",
        icon: getMenuSectionIcon("insert"),
        tooltip: "Insert",
        items: [
          { name: "horizontalRule", label: "Horizontal Rule" },
          { name: "codeBlock", label: "Code Block" },
          { name: "table", label: "Table" },
          { name: "link", label: "Link" },
        ],
      },
    ],
  },
  { name: "format", items: ["heading"] },
  // {
  //   name: "alignment",
  //   items: [
  //     {
  //       name: "textAlign",
  //       icon: getMenuSectionIcon("alignment"),
  //       items: ["textAlign"],
  //       tooltip: "Text Alignment",
  //       renderLabel: (t, alignment: TextAlignAlignment) => t(`editor.extensions.TextAlign.buttons.align_${alignment}.tooltip`),
  //     },
  //   ],
  // },
]

const allPresetSections = [
  { name: "history", items: ["history"] },
  { name: "insert", items: ["airalogyImage", "horizontalRule", "codeBlock", "table", "link"] },
  ...compactPresetSections.slice(2),
]
const sections = computed(() => {
  const result = [...basePresetSections]

  if (props.preset === "simple") {
    result.push(...simplePresetSections)
  }

  if (props.preset === "compact") {
    result.push(...compactPresetSections)
  }

  if (props.preset === "all") {
    result.push(...allPresetSections)
  }

  if (props.extraActions) {
    result.push(...props.extraActions)
  }

  return result
})

// Event handlers
function handleCompactItemSelect(key: string) {
  if (!key)
    return
  executeCompactAction(props.editor, key)
}
</script>

<style lang="scss" scoped>

</style>

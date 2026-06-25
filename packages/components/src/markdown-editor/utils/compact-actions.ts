import type { Editor } from "@tiptap/vue-3"
import type { Component } from "vue"

import HorizontalRuleIcon from "~icons/radix-icons/divider-horizontal"
import AlignLeft from "~icons/tabler/align-left"
import ArrowBack from "~icons/tabler/arrow-back"
// Import icons using the correct format as seen in extensions
import TextBold from "~icons/tabler/bold"
import Code from "~icons/tabler/code"
import IconEdit from "~icons/tabler/edit"
import Heading from "~icons/tabler/heading"
import IndentDecrease from "~icons/tabler/indent-decrease"
import IndentIncrease from "~icons/tabler/indent-increase"
import TextItalic from "~icons/tabler/italic"
import List from "~icons/tabler/list"
import ListCheck from "~icons/tabler/list-check"
import ListNumbers from "~icons/tabler/list-numbers"
import IconPlus from "~icons/tabler/plus"
import Select from "~icons/tabler/select"

import IconSettings from "~icons/tabler/settings"
import TextStrikethrough from "~icons/tabler/strikethrough"
import IconTextSize from "~icons/tabler/text-size"
import IconTools from "~icons/tabler/tools"
import Underline from "~icons/tabler/underline"

interface CompactAction {
  label: string
  icon?: Component
  action: (editor: Editor) => void
}

export const compactActions: Record<string, CompactAction> = {
  bold: {
    label: "Bold",
    icon: TextBold,
    action: (editor: Editor) => editor.chain().focus().toggleBold().run(),
  },
  italic: {
    label: "Italic",
    icon: TextItalic,
    action: (editor: Editor) => editor.chain().focus().toggleItalic().run(),
  },
  strike: {
    label: "Strike",
    icon: TextStrikethrough,
    action: (editor: Editor) => editor.chain().focus().toggleStrike().run(),
  },
  underline: {
    label: "Underline",
    icon: Underline,
    action: (editor: Editor) => editor.chain().focus().toggleUnderline().run(),
  },
  bulletList: {
    label: "Bullet List",
    icon: List,
    action: (editor: Editor) => editor.chain().focus().toggleBulletList().run(),
  },
  orderedList: {
    label: "Ordered List",
    icon: ListNumbers,
    action: (editor: Editor) => editor.chain().focus().toggleOrderedList().run(),
  },
  taskList: {
    label: "Task List",
    icon: ListCheck,
    action: (editor: Editor) => editor.chain().focus().toggleTaskList().run(),
  },
  horizontalRule: {
    label: "Horizontal Rule",
    icon: HorizontalRuleIcon,
    action: (editor: Editor) => editor.chain().focus().setHorizontalRule().run(),
  },
  codeBlock: {
    label: "Code Block",
    icon: Code,
    action: (editor: Editor) => editor.chain().focus().toggleCodeBlock().run(),
  },
  indent: {
    label: "Indent",
    icon: IndentIncrease,
    action: (editor: Editor) => editor.chain().focus().indent().run(),
  },
  outdent: {
    label: "Outdent",
    icon: IndentDecrease,
    action: (editor: Editor) => editor.chain().focus().outdent().run(),
  },
  selectAll: {
    label: "Select All",
    icon: Select,
    action: (editor: Editor) => editor.chain().focus().selectAll().run(),
  },
  heading: {
    label: "Heading",
    icon: Heading,
    action: (editor: Editor) => editor.chain().focus().toggleHeading({ level: 1 }).run(),
  },
  textAlign: {
    label: "Text Align",
    icon: AlignLeft,
    action: (editor: Editor) => editor.chain().focus().setTextAlign("left").run(),
  },
  history: {
    label: "History",
    icon: ArrowBack,
    action: (editor: Editor) => editor.chain().focus().undo().run(),
  },
}

export function executeCompactAction(editor: Editor, actionName: string): void {
  const action = compactActions[actionName]
  if (action) {
    action.action(editor)
  }
  else {
    console.warn(`No action found for ${actionName}`)
  }
}

// Helper function to get human-readable labels for menu items
export function getMenuItemLabel(item: string): string {
  return compactActions[item]?.label || item
}

// Add this back for backward compatibility
export function getMenuItemIcon(value: string): Component | null {
  return compactActions[value]?.icon || null
}

const formatIconRecord: Record<string, Component> = {
  format: IconEdit,
  alignment: AlignLeft,
  text: IconTextSize,
  indent: IndentIncrease,
  list: List,
  insert: IconPlus,
  operation: IconSettings,
  advanced: IconTools,
}

export function getMenuSectionIcon(value: string): Component | null {
  return formatIconRecord[value] || null
}

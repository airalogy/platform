<template>
  <menu-bar-item
    ref="popoverRef"
    :is-active="isActive"
    :enable-tooltip="enableTooltip"
    :tooltip="$t('editor.extensions.Table.tooltip')"
    :icon="Table"
  >
    <template #default="{ themeOverrides, handleClick, icon, label, triggerClass }">
      <create-table-popover :node="props.node" :editor="props.editor" @create-table="createTable">
        <template #trigger>
          <n-button
            :quaternary="!isActive"
            :secondary="isActive"
            :type="isActive ? 'primary' : 'default'"
            size="medium"
            :theme-overrides="themeOverrides"
            :class="triggerClass"
            @click="handleClick"
          >
            <template v-if="icon" #icon>
              <n-icon :component="icon" />
            </template>
            <span>{{ label }}</span>
          </n-button>
        </template>
      </create-table-popover>
    </template>
  </menu-bar-item>
</template>

<script setup lang="ts">
import type { Node } from "@tiptap/pm/model"
import type { Editor } from "@tiptap/vue-3"

import type { PopoverInst } from "naive-ui/es/popover"

import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"

import { $t } from "@airalogy/shared/locales"
import Table from "~icons/tabler/table"
import { enableMergeCells, enableSplitCell, isTableActive } from "../../utils/table"
import CreateTablePopover from "./create-table-popover.vue"

interface IProps {
  editor: Editor
  node: Node
}

const props = defineProps<IProps>()

const enableTooltip = inject("enableTooltip", true)
const popoverRef = ref<PopoverInst | null>(null)
const popoverVisible = ref(false)
function hidePopover() {
  const inst = unref(popoverRef)
  if (inst) {
    inst.setShow(false)
  }
}

const isActive = computed(() => {
  return isTableActive(props.editor.state)
})

const isMergeCellsEnabled = computed(() => {
  return enableMergeCells(props.editor.state)
})

const isSplitCellEnabled = computed(() => {
  return enableSplitCell(props.editor.state)
})

function createTable({ row, col }: { row: number, col: number }) {
  console.log("Before table insertion - editor state:", props.editor.state)

  props.editor.chain().insertTable({
    rows: row,
    cols: col,
    withHeaderRow: true,
  }).focus().command(({ tr }) => {
    console.log("After table insertion - transaction:", tr)
    console.log("Current selection:", props.editor.state.selection)
    return true
  }).insertContent({ type: "paragraph", content: [{ type: "text", text: "" }] }).command(({ tr }) => {
    console.log("After paragraph insertion attempt - transaction:", tr)
    console.log("Final selection:", props.editor.state.selection)
    return true
  }).run()

  console.log("After all commands executed")
  hidePopover()
}
</script>

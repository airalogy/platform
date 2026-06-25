<template>
  <n-popover
    v-model="popoverVisible"
    placement="right"
    trigger="click"
    popper-class="el-tiptap-popper"
    @after-leave="resetTableGridSize"
  >
    <!-- <div class="table-grid-size-editor">
      <div class="table-grid-size-editor__body">
        <div v-for="row in tableGridSize.row" :key="`r${row}`" class="table-grid-size-editor__row">
          <div
            v-for="col in tableGridSize.col"
            :key="`c-${col}`"
            :class="{
              'table-grid-size-editor__cell--selected':
                col <= selectedTableGridSize.col && row <= selectedTableGridSize.row,
            }"
            class="table-grid-size-editor__cell"
            @mouseover="selectTableGridSize(row, col)"
            @mousedown="confirmCreateTable(row, col)"
          >
            <div class="table-grid-size-editor__cell__inner" />
          </div>
        </div>
      </div>

      <div class="table-grid-size-editor__footer">
        {{ selectedTableGridSize.row }} X {{ selectedTableGridSize.col }}
      </div>
    </div> -->

    <table-view v-bind="nodeProps" />
    <template #trigger>
      <slot name="trigger">
        <div>
          {{ $t("editor.extensions.Table.buttons.insert_table") }}
        </div>
      </slot>
    </template>
  </n-popover>
</template>

<script setup lang="ts">
import type { Editor } from "@tiptap/core"
import type { Node } from "@tiptap/pm/model"
import type { NodeViewProps } from "@tiptap/vue-3"
import TableView from "./table-view.vue"

const props = defineProps<IProps>()
const emits = defineEmits<IEmits>()
const INIT_GRID_SIZE = 5
const MAX_GRID_SIZE = 10
const DEFAULT_SELECTED_GRID_SIZE = 2

interface IGridSize {
  row: number
  col: number
}

interface IProps {
  editor: Editor
  node: Node
}

const popoverVisible = ref(false)

interface IEmits {
  (e: "createTable", payload: { row: number, col: number }): void
}

function confirmCreateTable(row: number, col: number) {
  popoverVisible.value = false

  emits("createTable", { row, col })
}

const tableGridSize = ref<IGridSize>({
  row: INIT_GRID_SIZE,
  col: INIT_GRID_SIZE,
})

const selectedTableGridSize = ref<IGridSize>({
  row: DEFAULT_SELECTED_GRID_SIZE,
  col: DEFAULT_SELECTED_GRID_SIZE,
})

function selectTableGridSize(row: number, col: number) {
  if (row === tableGridSize.value.row) {
    tableGridSize.value.row = Math.min(row + 1, MAX_GRID_SIZE)
  }

  if (col === tableGridSize.value.col) {
    tableGridSize.value.col = Math.min(col + 1, MAX_GRID_SIZE)
  }

  selectedTableGridSize.value.row = row
  selectedTableGridSize.value.col = col
}

function resetTableGridSize() {
  tableGridSize.value = {
    row: INIT_GRID_SIZE,
    col: INIT_GRID_SIZE,
  }

  selectedTableGridSize.value = {
    row: DEFAULT_SELECTED_GRID_SIZE,
    col: DEFAULT_SELECTED_GRID_SIZE,
  }
}
const nodeProps = computed((): NodeViewProps => {
  return {
    node: props.node,
    decorations: [],
    selected: false,
    updateAttributes: () => {},
    deleteNode: () => {},
    editor: props.editor,
  } as unknown as NodeViewProps
})
</script>

<template>
  <menu-bar-item
    :enable-tooltip="enableTooltip"
    :tooltip="$t('editor.extensions.Table.tooltip')"
    :icon="Table"
    :disabled="disabled"
  >
    <template #default="{ isActive, handleClick, themeOverrides, icon }">
      <n-popover
        ref="popoverRef"
        placement="bottom"
        trigger="click"
      >
        <div class="table-grid-selector">
          <div
            class="table-grid-selector__grid"
            @mouseleave="resetHoverPosition"
          >
            <div
              v-for="index in tableSize.rows * tableSize.cols"
              :key="index"
              class="table-grid-selector__cell" :class="[
                { 'is-highlighted': isCellHighlighted(getRowFromIndex(index - 1), getColFromIndex(index - 1)) },
              ]"
              @mouseenter="handleCellHover(getRowFromIndex(index - 1), getColFromIndex(index - 1))"
              @click="handleCellClick(getRowFromIndex(index - 1), getColFromIndex(index - 1))"
            />
          </div>
          <div class="table-grid-selector__size-text">
            {{ hoverPosition.row + 1 }} × {{ hoverPosition.col + 1 }}
          </div>
        </div>
        <template #trigger>
          <n-button
            quaternary
            type="default"
            size="medium"
            :theme-overrides="themeOverrides"
            :disabled="props.disabled"
            @click="handleClick"
          >
            <template v-if="icon" #icon>
              <n-icon :component="icon" />
            </template>
          </n-button>
        </template>
      </n-popover>
    </template>
  </menu-bar-item>
</template>

<script setup lang="ts">
import type { Editor } from "@tiptap/vue-3"
import type { PopoverInst } from "naive-ui"
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import Table from "~icons/tabler/table"

defineOptions({ name: "TablePopover" })

const props = defineProps<Props>()

interface Props {
  editor: Editor
  command: (...args: any[]) => void
  disabled?: boolean
  name: string
}

const enableTooltip = inject("enableTooltip", true)

const popoverRef = ref<PopoverInst | null>(null)
const hoverPosition = ref({ row: 0, col: 0 })

const tableSize = {
  rows: 10,
  cols: 10,
}

const getRowFromIndex = (index: number) => Math.floor(index / tableSize.cols)
const getColFromIndex = (index: number) => index % tableSize.cols

function isCellHighlighted(row: number, col: number) {
  return row <= hoverPosition.value.row && col <= hoverPosition.value.col
}

function handleCellHover(row: number, col: number) {
  hoverPosition.value = { row, col }
}

function resetHoverPosition() {
  hoverPosition.value = { row: 0, col: 0 }
}

function handleCellClick(row: number, col: number) {
  props.command({
    rows: row + 1,
    cols: col + 1,
    withHeaderRow: true,
  })
  resetHoverPosition()
  popoverRef.value?.setShow(false)
}
</script>

<style lang="sass">
.table-grid-selector
  padding: 5px

  &__grid
    display: grid
    grid-template-columns: repeat(10, 1fr)
    gap: 2px
    margin-bottom: 8px

  &__cell
    width: 16px
    height: 16px
    border: 1px solid rgb(var(--border-color))
    cursor: pointer
    transition: all 0.2s ease
    border-radius: 2px

    &.is-highlighted
      background-color: rgba(var(--primary-color) / 80%)
      border-color: rgb(var(--primary-color))

  &__size-text
    text-align: center
    font-size: 12px
    color: rgb(var(--text-color))
</style>

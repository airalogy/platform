<template>
  <div
    class="items-container relative max-h-[160px] max-w-fit overflow-x-hidden overflow-y-auto rounded-lg bg-white p-1 text-sm shadow-lg"
  >
    <template v-if="querySubmenuItem">
      <n-input
        ref="queryInputRef"
        type="textarea"
        :rows="1"
        :placeholder="querySubmenuItem.description"
        class="w-60 resize-none border rounded-lg bg-white/10 p-2 font-inherit focus:outline-none"
        @keydown="handleQueryInputKeyDown"
      />
    </template>
    <template v-else>
      <div v-if="subMenuTitle" class="px-2 py-1 text-xs color-base-text">
        {{ subMenuTitle }}
      </div>
      <template v-if="allItems.length">
        <n-button
          v-for="(item, index) in allItems"
          :key="`${item.id}-${index}`"
          :ref="(el: any) => (itemRefs[index] = el)"
          :block="true"
          :type="selectedIndex === index ? 'primary' : 'default'"
          class="mention__option justify-start not-first:mt-0.5"
          :class="{ 'mention__option--selected': selectedIndex === index }"
          icon-placement="left"
          size="small"
          :theme-overrides="{
            border: '0',
            borderRadiusSmall: '6px',
          }"
          @click="selectItem(index)"
          @mouseenter="selectedIndex = index"
        >
          <template v-if="!item.icon" #icon>
            <template v-if="showFileIconForItem(item)">
              <icon-tabler-file />
              {{ item.label }}
            </template>

            <n-icon v-else :component="getDropdownIcon(item)" size="14" />
          </template>
          <component :is="item.icon" v-if="item.icon" />
          <span :title="item.id" class="pr-3">{{ item.title }}</span>
          <span
            class="invisible ml-auto opacity-0 transition-opacity duration-40 delay-80"
            :class="{ 'opacity-100 !visible': index === selectedIndex }"
          >
            {{ item.description }}
          </span>
          <arrow-right-icon
            v-if="item.type === 'contextProvider' && item.contextProvider?.type === 'submenu'"
            class="ml-2 h-[1.2em] w-[1.2em] flex-shrink-0"
          />
          <template v-if="item.subActions">
            <tooltip-button
              v-for="(subAction, actionIndex) in item.subActions"
              :key="actionIndex"
              :tooltip="subAction.label"
              :icon="ICONS_FOR_DROPDOWN[subAction.icon]"
              @click.stop="subAction.action(item); props.onClose()"
            />
          </template>
        </n-button>
      </template>
      <n-empty v-else description="No results found" />
    </template>
  </div>
</template>

<script setup lang="ts">
import type { Editor } from "@tiptap/vue-3"

import type { ComboBoxItem } from "./type"
import ArrowRightIcon from "~icons/heroicons/arrow-right"
import ArrowUpOnSquareIcon from "~icons/heroicons/arrow-up-on-square"
import AtSymbolIcon from "~icons/heroicons/at-symbol"
import BoltIcon from "~icons/heroicons/bolt"
import BookOpenIcon from "~icons/heroicons/book-open"
import CodeBracketIcon from "~icons/heroicons/code-bracket"
import CommandLineIcon from "~icons/heroicons/command-line"
import DocumentIcon from "~icons/heroicons/document"
import ExclamationCircleIcon from "~icons/heroicons/exclamation-circle"
import ExclamationTriangleIcon from "~icons/heroicons/exclamation-triangle"
import FolderIcon from "~icons/heroicons/folder"
import FolderOpenIcon from "~icons/heroicons/folder-open"
import GlobeAltIcon from "~icons/heroicons/globe-alt"
import HashtagIcon from "~icons/heroicons/hashtag"
import MagnifyingGlassIcon from "~icons/heroicons/magnifying-glass"
import PencilIcon from "~icons/heroicons/pencil"
import PlusIcon from "~icons/heroicons/plus"
import SparklesIcon from "~icons/heroicons/sparkles"
import TrashIcon from "~icons/heroicons/trash"
// import AddDocsDialog from "../dialogs/AddDocsDialog.vue"
// import HeaderButtonWithText from "../HeaderButtonWithText.vue"
import { type MaybeElement, unrefElement } from "@vueuse/core"

interface Props {
  items: ComboBoxItem[]
  command: (item: any) => void
  editor: Editor
  enterSubmenu?: (editor: Editor, providerId: string) => void
  onClose: () => void
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: "keydown", event: KeyboardEvent): void
}>()

const ICONS_FOR_DROPDOWN: { [key: string]: any } = {
  "file": FolderIcon,
  "code": CodeBracketIcon,
  "terminal": CommandLineIcon,
  "diff": PlusIcon,
  "search": MagnifyingGlassIcon,
  "url": GlobeAltIcon,
  "open": FolderOpenIcon,
  "codebase": SparklesIcon,
  "problems": ExclamationTriangleIcon,
  "folder": FolderIcon,
  "docs": BookOpenIcon,
  "issue": ExclamationCircleIcon,
  "trash": TrashIcon,
  "/edit": PencilIcon,
  "/clear": TrashIcon,
  "/comment": HashtagIcon,
  "/share": ArrowUpOnSquareIcon,
  "/cmd": CommandLineIcon,
  "/explain": DocumentIcon,
}

const selectedIndex = shallowRef<number>(0)
const subMenuTitle = ref<string>()
const querySubmenuItem = ref<ComboBoxItem>()
const allItems = ref<ComboBoxItem[]>([])
const queryInputRef = ref<HTMLTextAreaElement>()
const itemRefs = ref<Record<number, MaybeElement | null>>({})
// const selectedItem = computed(() => allItems.value[selectedIndex.value])

function getDropdownIcon(item: ComboBoxItem) {
  if (item.type === "action") {
    return PlusIcon
  }

  let provider: string = ""
  switch (item.type) {
    case "contextProvider":
    case "slashCommand":
      provider = item.id ?? ""
      break
    default:
      provider = item.type
      break
  }

  return ICONS_FOR_DROPDOWN[provider] ?? (item.type === "contextProvider" ? AtSymbolIcon : BoltIcon)
}

function selectItem(index: number) {
  const item = allItems.value[index]

  if (item.type === "action" && item.action) {
    item.action()
    return
  }

  if (item.type === "contextProvider" && item.contextProvider?.type === "submenu") {
    subMenuTitle.value = item.description
    if (item.id) {
      props.enterSubmenu?.(props.editor, item.id)
    }
    return
  }

  if (item.contextProvider?.type === "query") {
    const { tr } = props.editor.view.state
    const text = tr.doc.textBetween(0, tr.selection.from)
    const partialText = text.slice(text.lastIndexOf("@") + 1)
    const remainingText = item.title.slice(partialText.length)
    props.editor.view.dispatch(tr.insertText(remainingText, tr.selection.from))

    subMenuTitle.value = item.description
    querySubmenuItem.value = item
    return
  }

  if (item) {
    props.command({ ...item, itemType: item.type })
  }
}

function handleKeyDown({ event }: { event: KeyboardEvent }) {
  if (event.key === "ArrowUp") {
    if (selectedIndex.value > 0) {
      selectedIndex.value = Math.max(selectedIndex.value - 1, 0)

      const item = itemRefs.value[selectedIndex.value]
      if (!item) {
        return
      }
      const el = unrefElement(item)
      if (el) {
        el.scrollIntoView({ block: "nearest" })
      }
    }
    event.preventDefault()
    return true
  }

  if (event.key === "ArrowDown") {
    if (selectedIndex.value < allItems.value.length - 1) {
      selectedIndex.value = Math.min(selectedIndex.value + 1, allItems.value.length - 1)

      const item = itemRefs.value[selectedIndex.value]
      if (!item) {
        return
      }
      const el = unrefElement(item)
      if (el) {
        el.scrollIntoView({ block: "nearest" })
      }
    }
    event.preventDefault()
    return true
  }

  if (event.key === "Enter" || event.key === "Tab") {
    selectItem(selectedIndex.value)
    event.preventDefault()
    event.stopPropagation()
    return true
  }

  if (event.key === "Escape") {
    event.preventDefault()
    event.stopPropagation()

    return true
  }

  if (event.key === " " && allItems.value.length === 1) {
    selectItem(0)
    return true
  }

  return false
}

function handleQueryInputKeyDown(e: KeyboardEvent) {
  if (e.key === "Enter") {
    if (e.shiftKey) {
      queryInputRef.value!.value += "\n"
    }
    else {
      props.command({
        ...querySubmenuItem.value,
        itemType: querySubmenuItem.value?.type,
        query: queryInputRef.value?.value,
        label: `${querySubmenuItem.value?.label}: ${queryInputRef.value?.value}`,
      })
    }
  }
  else if (e.key === "Escape") {
    querySubmenuItem.value = undefined
    subMenuTitle.value = undefined
  }
}

watch(() => props.items, (items) => {
  const newItems = [...items]
  if (subMenuTitle.value === "Type to search docs") {
    newItems.push({
      title: "Add Docs",
      type: "action",
      action: () => {
        const { tr } = props.editor.view.state
        const text = tr.doc.textBetween(0, tr.selection.from)
        const start = text.lastIndexOf("@")
        props.editor.view.dispatch(tr.delete(start, tr.selection.from).scrollIntoView())
      },
      description: "Add a new documentation source",
    })
  }
  allItems.value = newItems

  // selectedIndex.value = 0
}, { immediate: true })

const showFileIconForItem = (item: ComboBoxItem) => ["file", "code"].includes(item.type)

defineExpose({
  onKeyDown: handleKeyDown,
})
</script>

<style lang="sass" scoped>
.items-container
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.05), 0px 10px 20px rgba(0, 0, 0, 0.1)

.mention__option :deep(.n-button__content)
  flex: 1

.mention__option--selected :deep(.option-field-tag)
  color: white!important
</style>

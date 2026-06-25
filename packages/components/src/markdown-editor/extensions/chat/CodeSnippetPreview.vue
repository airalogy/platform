<template>
  <div
    class="preview-markdown relative my-1 overflow-hidden rounded"
    :style="{ borderColor: borderColor || 'lightgray' }"
    spellcheck="false"
  >
    <div
      class="m-0 flex cursor-pointer items-center justify-between break-all border-b px-[5px] py-1.5 hover:opacity-90"
      :style="{ fontSize: '13px' }"
      @click="localHidden = !hidden"
    >
      <n-button
        class="flex items-center gap-1 hover:underline"
        @click.stop="handleShowFile"
      >
        <n-icon :component="fileIcon" :size="16" />
        {{ item.name }}
      </n-button>

      <div class="flex items-center gap-1">
        <tooltip-button
          :tooltip="hidden ? 'Show' : 'Hide'"
          :icon="hidden ? EyeIcon : EyeSlashIcon"
        />

        <tooltip-button
          tooltip="Delete"
          @click.stop="emit('remove')"
        >
          <x-mark-icon class="h-4 w-4" />
        </tooltip-button>
      </div>
    </div>

    <div
      ref="codeBlockRef"
      class="m-0" :class="[
        isSizeLimited ? 'overflow-hidden' : 'overflow-auto',
        { hidden },
      ]"
      :style="{ maxHeight: isSizeLimited ? `${MAX_PREVIEW_HEIGHT}px` : undefined }"
      contenteditable="false"
    >
      <styled-markdown-preview :source="source" />
    </div>

    <tooltip-button
      v-if="codeblockDims.height > MAX_PREVIEW_HEIGHT"
      class="absolute bottom-1 right-2"
      :tooltip="isSizeLimited ? 'Expand' : 'Collapse'"
      :icon="ChevronDownIcon"
      @click="isSizeLimited = !isSizeLimited"
    />
  </div>
</template>

<script setup lang="ts">
import type { ContextItemWithId } from "./type"
import TooltipButton from "@airalogy/components/tooltip-button.vue"
import { getFileSpecificIcon } from "@airalogy/shared/utils"
import { useResizeObserver } from "@vueuse/core"
import ChevronDownIcon from "~icons/heroicons/chevron-down-20-solid"
import EyeIcon from "~icons/heroicons/eye-20-solid"
import EyeSlashIcon from "~icons/heroicons/eye-slash-20-solid"
import XMarkIcon from "~icons/heroicons/x-mark-20-solid"

import StyledMarkdownPreview from "./StyledMarkdownPreview.vue"
// import { ctxItemToRifWithContents } from "./utils/commands"
import { dedent, getMarkdownLanguageTagForFile } from "./utils/doc"

interface IProps {
  item: ContextItemWithId
  inputId: string
  borderColor?: string
}

const props = defineProps<IProps>()

const emit = defineEmits<IEmits>()

interface IEmits {
  (e: "remove"): void
}

const MAX_PREVIEW_HEIGHT = 100
const backticksRegex = /`{3,}/g

const localHidden = ref<boolean | undefined>()
const isSizeLimited = ref(true)
const codeBlockRef = ref<HTMLDivElement>()
const codeblockDims = ref({ width: 0, height: 0 })

const content = computed(() => dedent`${props.item.content}`)
const fileIcon = computed(() => getFileSpecificIcon(props.item.name))

const fence = computed(() => {
  const backticks = content.value.match(backticksRegex)
  return backticks ? `${backticks.sort().at(-1)}\`` : "```"
})

const newestCodeblockForInputId = computed(() =>
  // store.session.newestCodeblockForInput[props.inputId],
  undefined,
)

const hidden = computed(() =>
  localHidden.value ?? newestCodeblockForInputId.value !== props.item.id.itemId,
)
const source = computed(() => {
  const languageTag = getMarkdownLanguageTagForFile(props.item.name)
  return `${fence.value + languageTag} ${props.item.description || ""}\n${content.value}\n${fence.value}`
})

useResizeObserver(codeBlockRef, (entries) => {
  const entry = entries[0]
  if (entry) {
    codeblockDims.value = {
      width: entry.contentRect.width,
      height: entry.contentRect.height,
    }
  }
})

function handleShowFile() {
  // TODO: Implement this
  // if (props.item.id.providerTitle === "file" && props.item.uri?.value) {
  //   window.postMessage({ type: "showFile", filepath: props.item.uri.value }, "*")
  // }
  // else if (props.item.id.providerTitle === "code") {
  //   const rif = ctxItemToRifWithContents(props.item, true)
  //   window.postMessage({
  //     type: "showLines",
  //     filepath: rif.filepath,
  //     startLine: rif.range.start.line,
  //     endLine: rif.range.end.line,
  //   }, "*")
  // }
  // else {
  //   window.postMessage({
  //     type: "showVirtualFile",
  //     content: content.value,
  //     name: props.item.name,
  //   }, "*")
  // }
}
</script>

<style lang="scss" scoped>
.preview-markdown {
  border-width: 0.5px;
  border-style: solid;
}
</style>

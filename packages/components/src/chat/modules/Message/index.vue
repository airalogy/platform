<!-- eslint-disable vue/no-v-html -->
<template>
  <define-action-button v-slot="{ tooltip, icon, onClick, showDivider, buttonClass, dividerClass }">
    <tooltip-button
      :tooltip="tooltip"
      :icon="icon"
      quaternary
      :class="buttonClass"
      @click="onClick"
    />
    <div v-if="showDivider" class="mx-1 h-2 w-px rounded bg-neutral-300" :class="dividerClass" />
  </define-action-button>

  <div
    v-if="props.message"
    ref="messageRef"
    class="group relative w-full flex"
    :class="[props.message.inversion ? 'flex-row-reverse pl-12' : 'pr-12', props.message.editing ? 'flex-1 pl-12!' : ''] "
    v-bind="$attrs"
  >
    <div
      v-if="!props.message.editing"
      class="h-10 flex flex-shrink-0 basis-10 items-center justify-center overflow-hidden rounded-full"
      :class="[props.message.inversion ? 'ml-2' : 'mr-2']"
    >
      <avatar-component :image="props.message.inversion ? props.userInfo?.avatar || '' : ''" :is-user="props.message.inversion" />
    </div>
    <div class="max-w-[calc(100%-3rem)] flex flex-1 flex-col" :class="[props.message.inversion ? 'flex-row-reverse' : '', props.message.editing ? 'mx-auto' : '']">
      <p
        class="absolute text-xs text-[#b4bbc4] opacity-0 transition-opacity -top-5 group-hover:opacity-100"
        :class="[props.message.inversion ? 'right-12' : 'left-12']"
      >
        {{ formatDate(props.message.dateTime, "date-time") }}
      </p>
      <stt-message
        v-if="audio"
        :text="props.message.text"
        :audio-url="audio"
        :inversion="props.message.inversion"
        :done="done"
      />
      <preset-cards
        v-else-if="props.message.presetAnswer"
        :content="props.message.presetAnswer"
      />
      <text-component
        v-else
        ref="textRef"
        :inversion="props.message.inversion"
        :error="props.message.error"
        :text="wholeContentRef[AnswerType.ANSWER].content"
        :loading="props.message.loading"
        :as-raw-text="asRawText"
        :editing="props.message.editing"
        :resolve-file="props.resolveFile"
        class="relative max-w-full"
        :class="[props.message.inversion ? 'ml-auto' : 'mr-auto', props.message.editing ? 'w-full' : '']"
        @update:editing="emit('update:editing', props.message, $event)"
        @save="emit('save', props.message, $event)"
      >
        <template v-if="props.message.attachments?.length && props.message.inversion" #prefix>
          <file-preview
            :attachments="props.message.attachments"
            :readonly="true"
            :max="props.message.attachments.length"
            :compact="true"
          />
        </template>
        <template v-else-if="!props.message.editing && props.message.error && props.message.errorMessage && props.message.inversion" #prefix>
          <tooltip-button :icon="IconIonRefreshOutline" size="tiny" tooltip="Retry" class="absolute top-2 h-6 w-6 -left-8" type="warning" circle @click="handleResent" />
        </template>

        <template #suffix>
          <n-collapse
            v-if="Array.isArray(searchResults) && searchResults.length > 0"
            v-model:expanded-names="expandReference"
            class="mt-3"
            :theme-overrides="{ titlePadding: '12px 0 0 0', itemMargin: '0 0 0 0 ' }"
          >
            <n-collapse-item
              v-for="(result, idx) in searchResults"
              :key="idx"
              :title="`Reference #${idx + 1}`"
              :name="idx"
              :class="{ 'opacity-30 hover:opacity-100': !expandReference.includes(idx) }"
            >
              <template #header-extra>
                <n-button quaternary @click.stop="handleOpenReference(result)">
                  <template #icon>
                    <n-icon :component="OpenOutline" />
                  </template>
                </n-button>
              </template>
              <div v-if="typeof result === 'string'" class="overflow-hidden text-ellipsis whitespace-pre-wrap break-all rounded-md bg-white p-3" v-html="result" />
              <div v-else-if="result.markdown" class="overflow-hidden text-ellipsis whitespace-pre-wrap break-all bg-white p-3">
                <aimd-markdown-preview
                  :content="result.markdown"
                  :mermaid-component="MermaidBlock"
                  body-class="markdown-body"
                />
              </div>
            </n-collapse-item>
          </n-collapse>
        </template>
      </text-component>
      <!-- Error message display -->
      <p v-if="props.message.error && props.message.errorMessage && props.message.inversion" class="ml-auto max-w-[min(100%,36rem)] w-fit whitespace-pre-line text-right text-xs text-red leading-5">
        {{ props.message.errorMessage }}
      </p>

      <div
        class="my-1 flex items-center transition-opacity"
        :class="[hasBranches ? 'mb-3' : 'invisible-item', props.message.inversion ? 'justify-end' : 'justify-start']"
      >
        <branch-switcher
          v-if="!props.message.inversion"
          :branches="branches"
          :active-branch-index="currentBranchIndex"
          class="mr-3"
          @switch-branch="handleSwitchBranch"
        />
        <reuse-action-button
          v-for="(button, index) in actionButtons"
          :key="button.content"
          :tooltip="button.content"
          :icon="button.icon"
          :on-click="button.onClick"
          :show-divider="index < actionButtons.length - 1"
          :button-class="['h-4 w-4 text-neutral-300 transition', isLastMessage ? '' : 'invisible-item']"
          :divider-class="[hasBranches || isLastMessage ? 'invisible-item' : '']"
        />
        <branch-switcher
          v-if="props.message.inversion"
          :branches="branches"
          :active-branch-index="currentBranchIndex"
          class="ml-3"
          @switch-branch="handleSwitchBranch"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { AimdMarkdownPreview } from "@airalogy/aimd-renderer/vue"
import MermaidBlock from "@airalogy/components/markdown-editor/modules/mermaid/mermaid-block.vue"
import TooltipButton from "@airalogy/components/tooltip-button.vue"
import { AnswerType, useClosableMessage, useLoading, useOpenNewTab, useTypewriterEffect } from "@airalogy/composables"
import { copyToClip } from "@airalogy/shared"
import { ChatType as ChatRole } from "@airalogy/shared/enum"
import { $t } from "@airalogy/shared/locales"
import { formatDate } from "@airalogy/shared/utils"

import { createReusableTemplate } from "@vueuse/core"

import PresetCards from "./PresetCards.vue"
// import IconIconParkOutlineThumbsDown from "~icons/icon-park-outline/thumbs-down"
// import IconIconParkOutlineThumbsUp from "~icons/icon-park-outline/thumbs-up"
import OpenOutline from "~icons/ion/open-outline"
import IconIonPencilOutline from "~icons/ion/pencil-outline"
import IconIonRefreshOutline from "~icons/ion/refresh-outline"
import IconCheck from "~icons/tabler/check"
import IconCopy from "~icons/tabler/copy"
import { NIcon } from "naive-ui"
import { useChatInfoStore } from "../../composables/useChatInfoStore"
import FilePreview from "../file-preview.vue"
import AvatarComponent from "./Avatar.vue"
import BranchSwitcher from "./BranchSwitcher.vue"
import SttMessage from "./stt-message.vue"
import TextComponent from "./Text.vue"

interface Props {
  message: Chat.ChatMessage
  chatId?: string
  resolveFile?: (id: string) => Promise<{ url: string } | null>
  userInfo?: {
    avatar?: string | null
  }
}

defineOptions({ inheritAttrs: false })
const props = defineProps<Props>()

const emit = defineEmits<Emits>()

export interface Emits {
  (e: "regenerate", item: Chat.ChatMessage): void
  (e: "remove"): void
  (e: "edit", item: Chat.ChatMessage): void
  (e: "continue", item: Chat.ChatMessage): void
  (e: "removeAttachment", fileId: string): void
  (e: "update:editing", item: Chat.ChatMessage, value: boolean): void
  (e: "save", item: Chat.ChatMessage, text: string): void
  (e: "resent", item: Chat.ChatMessage): void
  (e: "switchBranch", item: Chat.ChatMessage, branchIndex: number): void
  (e: "scrollToBottom", force?: boolean): void
}

const message = useClosableMessage()

const textRef = ref<HTMLElement>()

const asRawText = ref(false)

const messageRef = ref<HTMLElement>()

const { session, getLatestMessageId } = useChatInfoStore()!

// Simplified branch information - check if this message has branches
const hasBranches = computed(() => {
  const { childIndices } = props.message
  return childIndices && childIndices.length >= 1
})

// Get the current branch index for display
const currentBranchIndex = computed(() => {
  return props.message.currentChildIndex || 0
})

// Simplified: create minimal branch info for BranchSwitcher
const branches = computed(() => {
  const { childIndices } = props.message
  if (!childIndices || childIndices.length < 1) {
    return [props.message]
  }

  const messages = session.value?.data || []
  const branchMessages = childIndices
    .map(index => messages[index])
    .filter(Boolean)

  return branchMessages.length > 0 ? branchMessages : [props.message]
})

// Check if this is the last message in the conversation
const isLastMessage = computed(() => {
  const currentSession = toValue(session)
  if (!currentSession)
    return false

  const latestMessageIndex = getLatestMessageId(currentSession)
  return props.message.originalIndex === latestMessageIndex
})

// Simplified branch switching - just emit to parent
function handleSwitchBranch(branchMessage: Chat.ChatMessage, branchIndex?: number) {
  if (!props.chatId) {
    message.error("No chat ID")
    return
  }

  // Emit the switch branch event to be handled by the parent component
  const targetBranchIndex = branchIndex ?? 0
  emit("switchBranch", props.message, targetBranchIndex)
}

interface ToolResponse {
  search_results: string[]
  airalogy_protocols: { id: string, markdown: string, field_json_schema: Record<string, any> }[]
}
const searchResults = computed(() => {
  if (!props.message?.tool?.content) {
    return []
  }

  try {
    const response = JSON.parse(props.message.tool.content) as ToolResponse

    return (response.search_results || response.airalogy_protocols) as string[] | ToolResponse["airalogy_protocols"]
  }
  catch (e) {
    //
    return []
  }
})

function handleRegenerate() {
  messageRef.value?.scrollIntoView({ behavior: "smooth", block: "nearest" })
  emit("regenerate", props.message)
}

function handleResent() {
  emit("resent", props.message)
}
function handleContinue() {
  messageRef.value?.scrollIntoView({ behavior: "smooth", block: "nearest" })
  emit("continue", props.message)
}

const { loadingState, startTargetLoading, endTargetLoading } = useLoading()
async function handleCopy() {
  try {
    startTargetLoading("copy")
    await copyToClip(props.message?.text || "")
    message.success($t("chat.copied"))
  }
  catch {
    message.error($t("chat.copyFailed"))
  }
  finally {
    setTimeout(() => {
      endTargetLoading("copy")
    }, 1000)
  }
}
const expandReference = ref<number[]>([])

const [DefineActionButton, ReuseActionButton] = createReusableTemplate<{
  tooltip: string
  icon: Component
  onClick?: () => void
  showDivider?: boolean
  buttonClass?: HTMLAttributes["class"]
  dividerClass?: HTMLAttributes["class"]
}>()

interface ActionButton {
  content: string
  icon: Component
  onClick: () => void
}

const copyAction: ActionButton = {
  content: "Copy",
  icon: () => h(loadingState.value.copy ? IconCheck : IconCopy),
  onClick: handleCopy,
}
const regenerateAction: ActionButton = {
  content: "Regenerate",
  icon: IconIonRefreshOutline,
  onClick: handleRegenerate,
}
const editAction: ActionButton = {
  content: "Edit",
  icon: IconIonPencilOutline,
  onClick: () => emit("edit", props.message),
}

const isError = computed(() => {
  const { error, errorMessage, inversion } = props.message || {}
  if (!error || !errorMessage || !inversion) {
    return false
  }

  return true
})

// Define action buttons configuration
const actionButtons = computed(() => {
  const buttons: ActionButton[] = [
    copyAction,
  ]

  const { inversion } = props.message || {}
  if (inversion) {
    if (!isError.value) {
      buttons.push(editAction)
    }
  }
  else {
    buttons.push(regenerateAction)
  }
  return buttons
})

const audio = computed(() => {
  const { requestOptions, text } = props.message || {}
  if (requestOptions?.role === ChatRole.STT && text) {
    return text
  }

  return null
})

const done = computed(() => {
  const { requestOptions, text } = props.message || {}

  if (requestOptions?.role === ChatRole.STT && text) {
    return requestOptions.done
  }

  return false
})
const { openNewTab } = useOpenNewTab()
function handleRemoveAttachment(fileId: string) {
  emit("removeAttachment", fileId)
}

async function handleOpenReference(result: string | ToolResponse["airalogy_protocols"][number]) {
  if (typeof result === "string" || !result) {
    return
  }

  const { id } = result
  // openNewTab({
  //   name: "protocol-detail",
  //   params: {
  //     id,
  //   },
  // })
}

const { step, push, wholeContentRef } = useTypewriterEffect(
  {
    initContent: {
      answer: { content: props.message.text, length: props.message.text.length, prevLength: props.message.text.length },
      thinking: { content: "", length: 0, prevLength: 0 },
      allLength: props.message.text.length,
    },
    onTypedChar() {
      // Use smart scroll for streaming text (don't interrupt user viewing history)
      emit("scrollToBottom", true)
    },
  },
)

// Watch for source changes
watch(() => props.message.text, (newSource, prevSource = "") => {
  const updated = newSource.slice(prevSource.length)
  if (updated.length > 10) {
    step.value = 5
  }
  else {
    step.value = 1
  }

  push(updated)
})
</script>

<style scoped lang="sass">
.invisible-item, :deep(.invisible-item)
  @apply opacity-0 group-hover:opacity-100 invisible group-hover:visible
</style>

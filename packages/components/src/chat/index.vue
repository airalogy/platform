<template>
  <div class="size-full min-h-20 flex flex-col">
    <div class="flex-1 pb-4 pt-6" :class="contentClass">
      <template v-if="Array.isArray(session?.data) && session.data.length > 0">
        <!-- Load More Button -->
        <div v-if="hasMoreMessages" class="my-6 flex justify-center">
          <n-button
            text
            size="small"
            :loading="isLoadingMore"
            class="text-gray-400 hover:text-gray-600"
            @click="loadMoreMessages"
          >
            <template #icon>
              <n-icon size="16">
                <icon-ion-arrow-up />
              </n-icon>
            </template>
            {{ $t("chat.loadMoreMessages", { count: Math.min(PAGE_SIZE, allActiveMessages.length - loadedMessageCount) }) }}
          </n-button>
        </div>

        <!-- Messages -->
        <message-box
          v-for="branchMessage of activeMessages "
          :key="`${chatId}-${branchMessage.originalIndex}`"
          :message="branchMessage"
          :chat-id="chatId || ''"
          :user-info="userInfo"
          :resolve-file="props.resolveFile"
          @regenerate="handleRegenerate"
          @edit="handleEdit"
          @update:editing="handleUpdateEditing"
          @save="handleSave"
          @resent="handleResent"
          @switch-branch="handleSwitchBranch"
          @scroll-to-bottom="(force?: boolean) => emit('scrollToBottom', force)"
        />
      </template>
      <chat-placeholder v-else :examples="chatExamples" @example-click="handleStartNewChatWithExample" />
    </div>

    <div class="sticky bottom-0 z-10 w-full bg-white pt-2">
      <tooltip-button :class="{ '!opacity-0 pointer-events-none': props.showScrollButton }" :tooltip="$t('chat.scrollToBottom')" :button-props="{ tertiary: true, circle: true, size: 'small' }" class="absolute bottom-full left-1 mb-3 opacity-70 transition-all duration-300 hover:opacity-100" @click="emit('scrollToBottom')">
        <template #icon>
          <n-icon size="20">
            <icon-ion-chevron-down />
          </n-icon>
        </template>
      </tooltip-button>
      <chat-input :placeholder="inputPlaceholder" :source="props.source" :submit-handler="props.submitHandler" />
      <p class="py-2 text-center text-xs text-gray-500">
        {{ $t("chat.airaDisclaimer") }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useOrProvideShiki } from "@airalogy/composables"
import { type IProps, useOrProvideChatInfoStore } from "./composables/useChatInfoStore"
import ChatInput from "./modules/chat-input.vue"
import ChatPlaceholder from "./modules/chat-placeholder.vue"
import MessageBox from "./modules/Message/index.vue"
import { $t } from "@airalogy/shared/locales"

defineOptions({
  name: "ChatSessionInterface",
})

const props = withDefaults(defineProps<IProps & {
  contentClass?: any
  showScrollButton?: boolean
  resolveFile?: (id: string) => Promise<{ url: string } | null>
  submitHandler?: (value: string) => Promise<void> | void
}>(), {
  hideCollapse: false,
  fullScreen: false,
  enableToolAction: false,
  role: 1,
  couldChangeRole: true,
  contextSelectOptions: () => [],
  chatId: null,
  source: "global",
  resolveFile: undefined,
  protocolId: undefined,
  airalogyId: undefined,
  level: undefined,
  submitHandler: undefined,
})

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "scrollToBottom", isBottom?: boolean): void
}


const {
  emptyDraftId,
  session,
  handleRegenerate,
  prompt,
  handleAddNewSession,
  chatId,
  handleSubmit,
  handleResent,
  handleCreateEditBranch,
  userInfo,
  currentMessagePath,
} = useOrProvideChatInfoStore(toRefs(props), emit)

const inputPlaceholder = computed(() => $t("chat.inputPlaceholder"))
function handleUpdateEditing(branchMessage: Chat.ChatMessage, value: boolean) {
  branchMessage.editing = value
}

function handleSave(branchMessage: Chat.ChatMessage, prompt: string) {
  if (!prompt) {
    return
  }

  nextTick(() => {
    // handleResent(branchMessage, prompt)
    handleCreateEditBranch(branchMessage, prompt)
  })
}

function handleSwitchBranch(branchMessage: Chat.ChatMessage, branchIndex: number) {
  // Use navigation composable to handle branch switching
  const currentChat = session.value
  if (!currentChat) {
    return
  }

  // Update the parent message's current child index to switch branches
  const parentMessage = currentChat.data.find(msg =>
    msg.childIndices?.includes(branchMessage.originalIndex),
  )

  if (parentMessage) {
    parentMessage.currentChildIndex = branchIndex
  }
  else {
    // Handle root branch switching if needed
    console.warn("Root branch switching not yet implemented")
  }
}

const chatExamples = computed(() => {
  const baseExamples = [
    "What's new in Airalogy?",
    "How can you help me with my research?",
    "What features do you offer?",
  ]

  const { source } = props
  const docsBaseUrl = import.meta.env.VITE_DOCS_URL || "https://github.com/airalogy/platform/tree/main/docs"

  if (source === "protocol") {
    return [
      $t("chat.examples.protocol.brief"),
      $t("chat.examples.protocol.criticalPoints"),
      $t("chat.examples.protocol.optimize"),
      $t("chat.examples.protocol.safety"),
    ]
  }

  if (source === "record") {
    return [
      "Analyze my experiment data and suggest improvements",
      "Help me troubleshoot unexpected results",
      "What could be causing this variation in my data?",
      "Generate a summary report of my findings",
    ]
  }

  if (source === "discussion") {
    return [
      "What's the current status of my project?",
      "Help me plan the next experiments",
      "Analyze the trends across my experiments",
      "What conclusions can we draw from the data?",
    ]
  }

  if (source === "editor") {
    return [
      "Analyze my protocol and suggest improvements",
      "Help me fix the errors in my protocol",
      "Briefly explain the Airalogy Markdown syntax to me",
    ]
  }

  if (source === "hub") {
    return [
      $t("chat.examples.hub.tumorInhibition"),
      $t("chat.examples.hub.drugTreatmentAnalysis"),
      $t("chat.examples.hub.nanotechnology"),
    ]
  }

  if (source === "global") {
    return [
      {
        text: "What can Airalogy help me with?",
        presetResponse: JSON.stringify([
          {
            title: "Research Planning",
            description: "Protocol optimization and design.",
            link: `${docsBaseUrl}/getting-started`,
          },
          {
            title: "Data Analysis",
            description: "Visualize and analyze your data.",
            link: `${docsBaseUrl}/analysis`,
          },
        ]),
      },
      {
        text: "Show me the documentation",
        presetResponse: JSON.stringify([
          {
            title: "Getting Started",
            description: "A comprehensive guide to Airalogy.",
            link: `${docsBaseUrl}/getting-started`,
          },
          {
            title: "Protocol Management",
            description: "Learn how to manage your protocols.",
            link: `${docsBaseUrl}/protocols`,
          },
        ]),
      },
      {
        text: "How do I create my first protocol?",
        presetResponse: JSON.stringify([
          {
            title: "Protocol Creation Guide",
            description: "Step-by-step instructions.",
            link: `${docsBaseUrl}/protocols/create`,
          },
        ]),
      },
      {
        text: "How can I analyze my experimental data?",
        presetResponse: JSON.stringify([
          {
            title: "Data Analysis Docs",
            description: "Explore our data analysis tools.",
            link: `${docsBaseUrl}/analysis`,
          },
        ]),
      },
      {
        text: "Can you explain the collaboration features?",
        presetResponse: JSON.stringify([
          {
            title: "Collaboration Guide",
            description: "Learn how to collaborate with your team.",
            link: `${docsBaseUrl}/collaboration`,
          },
        ]),
      },
    ]
  }

  return baseExamples
})

function handleStartNewChatWithExample(example: Chat.Example) {
  const exampleText = typeof example === "string" ? example : example.text
  const presetResponse = typeof example === "string" ? null : example.presetResponse

  if (presetResponse) {
    const newChatId = handleAddNewSession()
    const userMessage: Chat.ChatMessage = {
      dateTime: Date.now(),
      text: exampleText,
      inversion: true,
      error: false,
      loading: false,
      requestOptions: { prompt: exampleText },
      originalIndex: 0,
      parentIndex: null,
      childIndices: [],
      currentChildIndex: 0,
    }
    const assistantMessage: Chat.ChatMessage = {
      dateTime: Date.now(),
      text: "",
      presetAnswer: presetResponse,
      inversion: false,
      error: false,
      loading: false,
      requestOptions: { prompt: "" },
      originalIndex: 1,
      parentIndex: 0,
      childIndices: [],
      currentChildIndex: 0,
    }
    session.value?.data.push(userMessage, assistantMessage)
  }
  else {
    handleAddNewSession()
    prompt.value = exampleText
    handleSubmit(exampleText)
    prompt.value = ""
  }
}

function handleEdit(item: Chat.ChatMessage) {
  item.editing = true
}

const { initializeShiki } = useOrProvideShiki({ themes: ["github-light"], langs: ["markdown", "json", "python"] })

// Pagination state
const PAGE_SIZE = 5
const loadedMessageCount = ref(PAGE_SIZE)
const isLoadingMore = ref(false)
const messageListRef = ref<HTMLElement | null>(null)
const isInitialLoad = ref(true)

// Function to build active conversation thread using navigation
const allActiveMessages = computed((): Chat.ChatMessage[] => {
  const list = toValue(session)?.data || []
  if (list.length === 0) {
    return []
  }

  const preFilteredList = list.filter((msg) => {
    const { inversion, cancelled, error, resent, regenerate } = msg
    if (inversion ? (resent || regenerate) : (cancelled || error)) {
      return false
    }
    return true
  })

  return preFilteredList
})

// Paginated messages - show only the latest N messages
const activeMessages = computed((): Chat.ChatMessage[] => {
  const messages = allActiveMessages.value
  if (messages.length <= loadedMessageCount.value) {
    return messages
  }
  // Return the last N messages
  return messages.slice(messages.length - loadedMessageCount.value)
})

const hasMoreMessages = computed(() => {
  return allActiveMessages.value.length > loadedMessageCount.value
})

function loadMoreMessages() {
  if (isLoadingMore.value)
    return

  // Find the parent scrollable container
  // Start from current element and traverse up to find overflow-y-auto with flex flex-col
  function findScrollableParent(element: HTMLElement | null): HTMLElement | null {
    if (!element)
      return null

    const parent = element.parentElement
    if (!parent)
      return null

    const style = window.getComputedStyle(parent)
    const hasOverflow = style.overflowY === "auto" || style.overflowY === "scroll"
    const hasScroll = parent.scrollHeight > parent.clientHeight

    if (hasOverflow && hasScroll) {
      return parent
    }

    return findScrollableParent(parent)
  }

  const currentEl = document.querySelector(".flex-1.pt-6") as HTMLElement
  const scrollContainer = findScrollableParent(currentEl)

  if (!scrollContainer) {
    console.warn("Scroll container not found")
    loadedMessageCount.value += PAGE_SIZE
    return
  }

  // Record the scroll position from bottom before loading
  const scrollHeightBefore = scrollContainer.scrollHeight
  const scrollTopBefore = scrollContainer.scrollTop
  const clientHeight = scrollContainer.clientHeight
  const scrollFromBottom = scrollHeightBefore - scrollTopBefore - clientHeight

  isLoadingMore.value = true

  // Small delay to simulate loading
  setTimeout(() => {
    loadedMessageCount.value += PAGE_SIZE

    // Wait for DOM update - use multiple checks
    nextTick(() => {
      // Try multiple times with increasing delays to ensure DOM is fully updated
      const attempts = [0, 50, 100, 200, 300]
      attempts.forEach((delay) => {
        setTimeout(() => {
          const scrollHeightAfter = scrollContainer.scrollHeight
          const newScrollTop = scrollHeightAfter - scrollFromBottom - clientHeight

          // Set scroll position directly
          scrollContainer.scrollTop = newScrollTop
        }, delay)
      })

      setTimeout(() => {
        isLoadingMore.value = false
      }, 350)
    })
  }, 300)
}

// Helper function to force scroll to bottom with multiple attempts (for async rendering)
function forceScrollToBottomWithRetry() {
  nextTick(() => {
    emit("scrollToBottom") // Force scroll (no parameter)
    setTimeout(() => emit("scrollToBottom"), 100)
    setTimeout(() => emit("scrollToBottom"), 300)
    setTimeout(() => emit("scrollToBottom"), 600)
  })
}

// Reset pagination and scroll when session changes
watch(() => toValue(session)?.uuid, (newUuid, oldUuid) => {
  if (newUuid && newUuid !== oldUuid) {
    loadedMessageCount.value = PAGE_SIZE
    isInitialLoad.value = true
    forceScrollToBottomWithRetry() // Force scroll on session change
  }
})

// Watch for messages being loaded and scroll to bottom (only on initial load or page refresh)
watch(() => activeMessages.value.length, (newLength) => {
  if (newLength > 0 && isInitialLoad.value) {
    forceScrollToBottomWithRetry() // Force scroll on initial load
    // Mark initial load as complete
    setTimeout(() => {
      isInitialLoad.value = false
    }, 800)
  }
}, { immediate: true })

// Watch for new messages (streaming) and smart scroll (exclude load more scenarios)
watch(() => allActiveMessages.value.length, (newLength, oldLength) => {
  if (newLength > oldLength && !isLoadingMore.value) {
    nextTick(() => {
      emit("scrollToBottom", true) // Smart scroll for streaming content
    })
  }
})

onMounted(async () => {
  await initializeShiki()
})
</script>

<style lang="sass" scoped>
.drag-handle
  @apply bg-gray-50 border-b border-gray-200 px-2 py-1 cursor-move h-fit flex items-center

:deep(.n-popover)
  max-width: none
  padding: 0

:deep(.n-popover-content)
  padding: 0

.n-button
  &.n-button--text-type
    padding: 0.375rem 0.75rem
    border-radius: 0.5rem

    .n-button__icon
      margin-right: 0.5rem
      font-size: 1rem

    &:hover
      background-color: var(--n-color-hover)
</style>

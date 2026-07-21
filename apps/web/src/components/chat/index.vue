<template>
  <chat-wrapper :full-screen="fullScreen" :docked="docked">
    <template #default="{ contentClass }">
      <div
        v-show="!collapsed || fullScreen || docked"
        v-bind="$attrs"
        ref="chatContainer"
        class="flex flex-col"
        :style="!fullScreen && docked ? { left: `${x}px`, top: `${y}px` } : undefined"
        :class="[!fullScreen && !docked && 'overflow-y-auto', contentClass]"
      >
        <div
          v-if="!fullScreen && docked"
          ref="dragHandleRef"
          class="drag-handle sticky top-0 z-20"
        >
          <div class="group relative flex-1 whitespace-nowrap pl-3 text-lg">
            {{ $t("chat.askAira") }}
            <span class="absolute-y-center pl-1 text-xs text-gray-500 opacity-0 transition-all duration-300 group-hover:opacity-100">
              {{ $t("chat.dragToMove") }}
            </span>
          </div>
          <chat-wrapper-actions v-bind="chatWrapperActionProps" v-on="chatWrapperActionEventHandlers" />
        </div>
        <div v-else-if="fullScreen" class="relative h-12 w-full bg-white">
          <protocol-title-section v-if="fullScreen" :protocol-info="protocolInfo" :title="protocolInfo?.name" :show-icon="false" size="small" class="size-full" content-class="justify-center max-w-[800px] mx-auto" />
          <chat-wrapper-actions v-bind="chatWrapperActionProps" v-on="chatWrapperActionEventHandlers" />
        </div>
        <chat-wrapper-actions v-else v-bind="chatWrapperActionProps" v-on="chatWrapperActionEventHandlers" />
        <chat-interface
          ref="chatRef"
          v-model:collapsed="collapsed"
          v-model:full-screen="fullScreen"
          v-model:docked="docked"
          v-model:role="role"
          v-model:chat-id="chatId"
          :source="source"
          :class="[fullScreen ? 'container m-auto' : 'px-2', docked || fullScreen ? 'overflow-y-auto' : 'scrollable']"
          :show-scroll-button="arrivedState.bottom"
          :resolve-file="props.resolveFile"
          @scroll-to-bottom="handleScrollToBottom"
        />
        <context-select-dialog :source="source" v-bind="contextDialog" v-on="contextDialogEventHandlers" />
      </div>
    </template>
  </chat-wrapper>
</template>

<script setup lang="tsx">
import type { ChatProviderProps } from "@airalogy/components/chat/providers/useChatProvider"
import type { DropdownOption } from "naive-ui"
import ProtocolTitleSection from "@/components/Layout/protocol-title-section.vue"
import { useProtocolInfoStoreWithDefaultValue } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import { useScroll } from "@airalogy/components/chat/composables"
import { type IProps, useOrProvideChatInfoStore } from "@airalogy/components/chat/composables/useChatInfoStore"
import ChatInterface from "@airalogy/components/chat/index.vue"
import ChatWrapper from "@airalogy/components/chat/modules/chat-wrapper.vue"
import ChatWrapperActions from "@airalogy/components/chat/modules/chat-wrapper-actions.vue"
import { ChatType } from "@airalogy/shared/enum"
import { useDraggable, useVModel } from "@vueuse/core"
import DocumentIcon from "~icons/fluent/document-20-regular"
import RemoveIcon from "~icons/ion/trash-bin-outline"
import LabIcon from "~icons/local/lab-outline"
import DiscussionIcon from "~icons/local/message-outline"
import ProjectIcon from "~icons/local/project-outline"
import ProtocolIcon from "~icons/local/protocol-outline"
import RecordIcon from "~icons/local/record-outline"
import { NIcon } from "naive-ui"
import { useOrProvideChatConfigStore, useScrollTrap } from "../../composables"
import { capitalCase } from "../../utils/changeCase"
import ContextSelectDialog from "./modules/context-select-dialog.vue"

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<IProps & ActionProps & {
  resolveFile?: (id: string) => Promise<{ url: string } | null>
}>(), {
  hideCollapse: false,
  collapsed: false,
  fullScreen: false,
  enableToolAction: false,
  role: 1,
  couldChangeRole: true,
  contextSelectOptions: () => [],
  chatId: null,
  source: "global",
  docked: false,
  resolveFile: undefined,
})

const emit = defineEmits<{
  (e: "update:collapse", collapse: boolean): void
  (e: "update:role", role: 1 | 2): void
  (e: "update:fullScreen", fullScreen: boolean): void
  (e: "update:collapsed", collapsed: boolean): void
  (e: "update:docked", docked: boolean): void
}>()

export interface ActionProps {
  hideCollapse?: boolean
  collapsed?: boolean
  fullScreen?: boolean
  docked?: boolean
}

// Add refs for draggable functionality
const chatContainer = ref<HTMLElement | null>(null)
const chatRef = ref<HTMLElement | null>(null)
const dragHandleRef = ref<HTMLElement | null>(null)

// Add scroll trapping to prevent parent scrolling
const { measure, scrollToBottom, scrollRef, arrivedState } = useScroll(chatContainer)
useScrollTrap(scrollRef)

const contentRef = ref<HTMLElement | null>(null)
watch([() => scrollRef.value?.clientHeight, () => contentRef.value?.clientHeight], () => {
  setTimeout(() => {
    measure()
    scrollToBottom({ smart: false, instant: true })
  }, 200)
}, { flush: "post", immediate: true })

function handleScrollToBottom(smart?: boolean) {
  scrollToBottom({ smart: smart ?? false, instant: true })
}

const {
  session,

  prompt,
  context,
  chatId,
  clearActive,
  updateContext,
  contextDialog,
  contextOptions,
  contextDialogEventHandlers,
  source,
  selectedRole,
  protocolId,
} = useOrProvideChatInfoStore(toRefs(props), (event, smart) => {
  if (event === "scrollToBottom") {
    handleScrollToBottom(smart)
  }
})

// Use useDraggable from VueUse
const { position } = useDraggable(dragHandleRef, {
  preventDefault: true,
  handle: dragHandleRef,
})
const { width, height } = useWindowSize()
const x = computed(() => {
  const container = unrefElement(chatContainer)
  if (!container) {
    return 0
  }

  return Math.max(0, Math.min(position.value.x, width.value - container.offsetWidth))
})

const y = computed(() => {
  const container = unrefElement(chatContainer)
  if (!container) {
    return 0
  }

  return Math.max(0, Math.min(position.value.y, height.value - container.offsetHeight))
})

const collapsed = useVModel(props, "collapsed", emit, { defaultValue: false })
const fullScreen = useVModel(props, "fullScreen", emit, { defaultValue: false })
const docked = useVModel(props, "docked", emit, { defaultValue: false })
const role = useVModel(props, "role", emit, { defaultValue: ChatType.NORMAL })

watch(() => docked.value || fullScreen.value, (val) => {
  if (val) {
    scrollRef.value = unrefElement(chatRef) || null
  }
  else {
    scrollRef.value = chatContainer.value || null
  }

  measure()
}, { immediate: true, flush: "post" })

function handleFullScreen() {
  docked.value = false
  fullScreen.value = !fullScreen.value
}

function handleDock() {
  const container = unrefElement(chatContainer)
  if (container) {
    if (docked.value) {
      position.value.x = 0
      position.value.y = 0
    }
    else {
      const rect = container.getBoundingClientRect()
      position.value.x = rect.x
      position.value.y = rect.y
    }
  }

  fullScreen.value = false

  collapsed.value = !docked.value
  docked.value = !docked.value
}

function handleToggleCollapse() {
  collapsed.value = !collapsed.value
  fullScreen.value = false
  docked.value = false
}

function handleStartNewChat() {
  if (session.value) {
    prompt.value = ""
  }

  clearActive()
}

const { protocolInfo } = useProtocolInfoStoreWithDefaultValue()

watch([protocolInfo, chatId], ([info]) => {
  if (!info) {
    return
  }

  const { lab, project, uid, id, name } = info
  protocolId.value = id
  const ctx = toValue(context)

  if (ctx && ctx.findIndex(item => item.id === id) === -1) {
    const contextItem: Chat.ChatProtocolContext = {
      id,
      type: "protocol",
      airalogyId: id,
      item: info,
      removable: false,
      isLocal: true,
      lab,
      project,
      protocol: { name, uid, id },
    }

    // ctx.push(contextItem)
    updateContext([...ctx, contextItem])
  }
}, { immediate: true, flush: "post" })

// Reset position when switching modes
// watch([collapsed, fullScreen, docked], ([newCollapsed, newFullScreen, newDocked]) => {
//   if (newFullScreen) {
//     return
//   }

//   if (newCollapsed) {
//     fullScreen.value = false
//     if (!newDocked) {
//       docked.value = false
//     }

//     return
//   }

//   if (newDocked) {
//     if (newFullScreen) {
//       collapsed.value = false
//     }
//     else {
//       collapsed.value = true
//     }
//   }
// }, { immediate: true })

watch(docked, (val) => {
  emit("update:docked", val)
}, { immediate: true })

// // Adjust position on window resize to keep chat visible
// useEventListener(window, "resize", () => {
//   if (!fullScreen.value && !docked.value && chatContainer.value) {
//     x.value = Math.max(0, Math.min(x.value, window.innerWidth - chatContainer.value.offsetWidth))
//     y.value = Math.max(0, Math.min(y.value, window.innerHeight - chatContainer.value.offsetHeight))
//   }
// })

const chatWrapperActionProps = computed(() => ({
  fullScreen: fullScreen.value,
  docked: docked.value,
  collapsed: collapsed.value,
  hideCollapse: props.hideCollapse,
  containerClass: fullScreen.value ? "absolute-y-center right-4 space-x-1" : docked.value ? "w-fit" : "absolute right-4 top-0 space-x-1",
}))

const chatWrapperActionEventHandlers = computed(() => ({
  toggleCollapse: handleToggleCollapse,
  toggleDock: handleDock,
  toggleFullscreen: handleFullScreen,
  newChat: handleStartNewChat,
}))

function handleConfirmContexts(
  selected: (Chat.ChatContext & { version: number })[],
) {
  if (!context.value) {
    updateContext(selected)

    return
  }
  const set = new Set(context.value.map(item => item.id))

  const updatedContext = [...context.value]
  selected.forEach((item) => {
    if (set.has(item.id)) {
      return
    }

    updatedContext.push(item)
  })
  updateContext(updatedContext)
}

const {
  enableDiscussion,
  discussionScope,
} = useOrProvideChatConfigStore()

// Non-protocol chat contexts should not auto-enable discussion context.
watch(source, (val) => {
  if (val === "protocol") {
    enableDiscussion.value = true
    discussionScope.value = "protocol"
    return
  }

  if (val === "hub" || val === "global") {
    enableDiscussion.value = false
    discussionScope.value = "protocol"
  }
}, { immediate: true })

const discussionOptions: DropdownOption[] = [
  {
    label: "Discussions in the protocol",
    key: "protocol",
    icon: () => h(NIcon, null, { default: () => h(ProtocolIcon) }),
  },
  {
    label: "Discussions in the project",
    key: "project",
    icon: () => h(NIcon, null, { default: () => h(ProjectIcon) }),
  },
  {
    label: "Discussions in the lab",
    key: "lab",
    icon: () => h(NIcon, null, { default: () => h(LabIcon) }),
  },
  {
    label: "Remove discussion context",
    key: "remove",
    icon: () => h(NIcon, { size: 14 }, { default: () => h(RemoveIcon) }),
  },
]

function handleDiscussionSelect(key: "protocol" | "project" | "lab" | "remove") {
  if (key === "remove") {
    enableDiscussion.value = false
    discussionScope.value = "protocol"
  }
  else {
    discussionScope.value = key
  }
}

function handleDiscussionContext() {
  enableDiscussion.value = !enableDiscussion.value
}

watch(() => !enableDiscussion.value, (val) => {
  const discussionIdx = contextDialog.value.options.findIndex(({ value }) => value === "discussion")

  if (val) {
    if (discussionIdx !== -1) {
      contextDialog.value.options.splice(discussionIdx, 1)
    }

    return
  }

  if (discussionIdx === -1) {
    contextDialog.value.options.push({
      label: discussionScope.value,
      value: "discussion",
      component: () => (
        (
          <n-dropdown placement="top-start" options={discussionOptions} onSelect={handleDiscussionSelect}>
            <n-tag
              class="cursor-pointer"
              onClose={handleDiscussionContext}
              v-slots={{ icon: () => (
                <n-icon size="16">
                  <icon-local-message-outline />
                </n-icon>
              ),
              }}
            >

              <span class="align-middle">
                {`${capitalCase(discussionScope.value)} Discussions`}
              </span>

              <n-icon size="16" class="ml-1 align-middle">
                <icon-ion-chevron-up />
              </n-icon>
            </n-tag>
          </n-dropdown>
        )

      ),
    })
  }
}, { immediate: true })

watch(source, (val) => {
  if (val === "editor") {
    return [{
      label: "Documents",
      key: "document",
      icon: () => h(NIcon, null, { default: () => h(DocumentIcon) }),
    }]
  }

  const options: ChatProviderProps["contextOptions"] = [
    {
      label: "Records",
      key: "record",
      icon: () => h(NIcon, null, { default: () => h(RecordIcon) }),
    },
    {
      label: "Protocols",
      key: "protocol",
      icon: () => h(NIcon, null, { default: () => h(ProtocolIcon) }),
    },
  ]

  options.push({
    label: "Discussion",
    key: "discussion",
    icon: () => h(NIcon, null, { default: () => h(DiscussionIcon) }),
  })

  contextOptions.value = options
}, { immediate: true })

watch([protocolInfo, () => contextDialog.value.type], ([info, type]) => {
  if (!info) {
    return []
  }

  const { lab, project, id, name } = info
  const isLeaf = type !== "record"

  const protocolNode = isLeaf
    ? undefined
    : {
        label: name,
        value: `${lab.id}_${project.id}_${id}`,
        depth: 3,
        isLeaf: true,
      }

  const projectNode = {
    label: project.name,
    value: `${lab.id}_${project.id}`,
    depth: 2,
    isLeaf,
    uid: project.uid,
    children: protocolNode ? [protocolNode] : [],
  }

  const labNode = {
    label: lab.name,
    value: lab.id,
    depth: 1,
    isLeaf: false,
    uid: lab.uid,
    children: [projectNode],
  }

  contextDialog.value.readonlyList = [id]
  contextDialog.value.defaultSelectedOptions = [labNode]
  contextDialog.value.defaultSelectedPath = protocolNode?.value || projectNode.value
}, { immediate: true })

watch(context, (val) => {
  if (!val) {
    contextDialog.value.selected = []
    return
  }

  contextDialog.value.selected = val.map(it => it.id)
})
onMounted(() => {
  measure()
  scrollToBottom({ smart: false, instant: true })

  contextDialogEventHandlers.value.confirm = handleConfirmContexts
})

defineExpose({
  setDocked: (val: boolean) => {
    docked.value = val
  },
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

.scrollable
  scrollbar-gutter: stable
</style>

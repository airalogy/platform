<template>
  <div
    class="min-h-10 w-full flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-lg px-2 py-1 transition-all duration-300"
    :class="{ 'w-fit font-0': isContextCollapsed, 'bg-gray-100': !isContextCollapsed && Array.isArray(context) && context.length > 0 }"
  >
    <n-dropdown trigger="hover" placement="bottom-start" :options="enhancedContextOptions" :disabled="isRecording" @select="handleContextMenuSelect">
      <n-button
        class="min-h-8" quaternary size="small" :theme-overrides="{
          heightSmall: 'fit-content',
          paddingSmall: '0 8px',
          borderRadiusSmall: '8px',
        }"
      >
        <template #icon>
          <n-icon>
            <icon-ion-add-outline />
          </n-icon>
        </template>
        <span v-if="isContextCollapsed">Add context</span>
      </n-button>
    </n-dropdown>

    <!-- Hidden upload input -->
    <div style="display: none;">
      <n-upload
        :show-file-list="false"
        :custom-request="handleUpload"
        accept="image/jpeg,image/jpg,image/png,image/gif,.pdf"
        :disabled="isRecording"
      >
        <n-button ref="uploadTriggerRef">
          Upload
        </n-button>
      </n-upload>
    </div>

    <template v-if="!isContextCollapsed">
      <!-- Context Tags -->
      <template v-if="contextTags && contextTags.length > 0">
        <template v-for="tag in contextTags" :key="tag.value">
          <component :is="tag.option.component" v-if="tag.option?.component" />
          <context-tag
            v-else-if="tag.context" :context="tag.context" class="h-full"
            :closeable="tag.removable" @close="handleRemoveContext" @navigate="handleNavigateToContext"
          />
          <n-tag v-else closable @close="handleRemoveContext(tag.value)">
            {{ tag.label }}
          </n-tag>
        </template>
      </template>
    </template>

    <n-button v-if="context" quaternary class="flex-0 ml-auto" icon-placement="right" size="small" @click="isContextCollapsed = !isContextCollapsed">
      <template v-if="isContextCollapsed">
        <span>Current: {{ contextTags.length }}</span>
        <span v-if="pendingContexts && pendingContexts.length > 0" class="ml-1 text-[10px] color-text-secondary">(pending {{ pendingContexts.length }})</span>
      </template>
      <template #icon>
        <n-icon :size="14">
          <icon-ion-chevron-down v-if="isContextCollapsed" />
          <icon-ion-chevron-up v-else />
        </n-icon>
      </template>
    </n-button>
  </div>
</template>

<script setup lang="ts">
import type { DropdownOption } from "naive-ui"
import type { ContextDialogStateOption } from "../../providers/useChatProvider"
import { nextTick } from "vue"
// import { useProtocolInfoStore } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import { useChatInfoStore } from "@airalogy/components/chat/composables/useChatInfoStore"
import UploadIcon from "~icons/ion/attach"
import { NButton, NDropdown, NIcon, NTag, NUpload } from "naive-ui"
// import ContextSelectDialog from "../context-select-dialog.vue"
import ContextTag from "../context-tag.vue"

interface IProps {
  source: Chat.ChatSource
  dry?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  dry: false,
})

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "navigate", action: "open-new-tab" | "navigate-to-context", payload: Chat.ChatContext): void
}

interface TagOption {
  label: string
  value: string
  removable?: boolean
  context?: Chat.ChatContext
  option?: ContextDialogStateOption
}

// const showContextDialog = ref(false)
// const contextSelectOptions = ref<SelectOption[]>([])
const selectedContexts = ref<string[]>([])
const isContextCollapsed = ref(false)
const uploadTriggerRef = ref<any>(null)

const chatInfoStore = useChatInfoStore()!
const {
  context,
  isRecording,
  updateContext,
  contextDialog,
  contextOptions,
  contextDialogEventHandlers,
  handleUpload,
} = chatInfoStore

// const { routerPushByKey } = useRouterPush()
// const { protocolInfo } = useProtocolInfoStore() || {}

const pendingContexts = computed(() => {
  return context.value?.filter(item => item.removable)
})

// Initialize selectedContexts when dialog opens
watch(() => contextDialog.value.show, (show) => {
  if (show && context.value) {
    selectedContexts.value = context.value.map(item => item.id) || []
  }
})

// Add computed property to detect Field Input mode
// const isFieldInputMode = computed(() => {
//   return selectedRole.value === ChatType.FIELD_INPUT || session.value?.role === ChatType.FIELD_INPUT
// })

// Automatically disable discussions when switching to Field Input mode
// watch(isFieldInputMode, (isFieldInput) => {
//   if (isFieldInput && enableDiscussion.value) {
//     enableDiscussion.value = false
//     discussionScope.value = "protocol"
//   }
// })

function getContextItem(id: string) {
  const list = context.value
  return list?.find(item => item.id === id)
}

function handleNavigateToContext(id: string) {
  const item = getContextItem(id)
  if (!item)
    return
  const { lab, project, protocol } = item
  if (!lab || !project || !protocol) {
    return
  }

  if (props.dry) {
    emit("navigate", "open-new-tab", item)
  }
  else {
    emit("navigate", "navigate-to-context", item)
  }
}

async function handleRemoveContext(id: string) {
  if (Array.isArray(context.value)) {
    const newContexts = context.value.filter(item => item.id !== id)
    updateContext(newContexts)
  }
  else {
    updateContext([])
  }
}

// Enhanced context options with Upload File
const enhancedContextOptions = computed((): DropdownOption[] => {
  const baseOptions = contextOptions.value || []
  return [
    ...baseOptions,
    {
      type: "divider",
      key: "divider",
    },
    {
      label: "Upload File",
      key: "uploadFile",
      icon: () => h(NIcon, null, { default: () => h(UploadIcon) }),
    },
  ]
})

function handleContextMenuSelect(key: string) {
  if (key === "uploadFile") {
    // Trigger the hidden upload button
    nextTick(() => {
      uploadTriggerRef.value?.$el?.click()
    })
  }
  else {
    // Handle other context options
    if (contextDialogEventHandlers.value.selectType) {
      contextDialogEventHandlers.value.selectType(key)
    }
    else {
      handleDropdownSelect(key)
    }
  }
}

function handleDropdownSelect(key: string) {
  // @ts-expect-error key is not typed
  contextDialog.value.type = key
  contextDialog.value.show = true
}

const contextTags = computed(() => {
  const list = context.value
  if (!list) {
    return []
  }

  const result = list.map((item): TagOption => {
    return {
      label: item.id.slice(0, 10),
      value: item.id,
      removable: item.removable,
      context: item,
    }
  }).sort((a, b) => {
    if (a.removable && !b.removable)
      return 1
    if (!a.removable && b.removable)
      return -1
    return 0
  })

  if (contextDialog.value.options) {
    contextDialog.value.options.forEach((option) => {
      const { label, value, removable } = option

      const target = list.find(it => it.id === value)

      result.push({
        label,
        value,
        removable: Boolean(removable),
        context: target,
        option,
      })
    },
    )
  }
  return result
})

// const discussionOptions: DropdownOption[] = [
//   {
//     label: "Discussions in the protocol",
//     key: "protocol",
//     icon: () => h(NIcon, null, { default: () => h(ProtocolIcon) }),
//   },
//   {
//     label: "Discussions in the project",
//     key: "project",
//     icon: () => h(NIcon, null, { default: () => h(ProjectIcon) }),
//   },
//   {
//     label: "Discussions in the lab",
//     key: "lab",
//     icon: () => h(NIcon, null, { default: () => h(LabIcon) }),
//   },
//   {
//     label: "Remove discussion context",
//     key: "remove",
//     icon: () => h(NIcon, { size: 14 }, { default: () => h(RemoveIcon) }),
//   },
// ]

// function handleDiscussionSelect(key: "protocol" | "project" | "lab" | "remove") {
//   if (key === "remove") {
//     enableDiscussion.value = false
//     discussionScope.value = "protocol"
//   }
//   else {
//     discussionScope.value = key
//   }
// }
</script>

<style lang="sass" scoped>
.context-tags
  display: flex
  flex-wrap: wrap
  gap: 0.5rem
  align-items: center

  &:not(:empty)
    margin-top: 0.25rem
    margin-bottom: 0.25rem
</style>

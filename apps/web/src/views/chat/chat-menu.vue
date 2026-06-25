<template>
  <div class="global-menu h-full flex flex-col border-r border-gray-200 bg-white">
    <!-- New Chat Button -->
    <div class="border-b border-gray-100 p-2">
      <n-button type="primary" block @click="handleNewChat">
        <template #icon>
          <n-icon>
            <icon-ion-add />
          </n-icon>
        </template>
        <span v-if="!appStore.siderCollapse">{{ $t("chat.newChatButton") }}</span>
      </n-button>
    </div>

    <!-- Menu Navigation -->
    <nav class="flex-1 overflow-hidden">
      <div v-if="!appStore.siderCollapse" class="h-full">
        <chat-history-sidebar />
      </div>
      <div v-else class="mt-3">
        <tooltip-button
          :button-props="{ quaternary: true, block: true }"
          :tooltip="$t('chat.history')"
          class="w-full"
          @click="appStore.toggleSiderCollapse"
        >
          <template #icon>
            <n-icon size="20">
              <icon-ion-time-outline />
            </n-icon>
          </template>
        </tooltip-button>
      </div>
    </nav>

    <!-- Menu Footer -->
    <div class="border-t border-gray-100">
      <tooltip-button quaternary block :tooltip="$t('page.hub.openHub')" @click="openNewTab({ name: 'hub' })">
        <template #icon>
          <n-icon :size="20">
            <icon-shared-protocol-outline />
          </n-icon>
        </template>
        <template v-if="!appStore.siderCollapse">
          {{ $t("page.hub.title") }}
        </template>
      </tooltip-button>
      <tooltip-button quaternary block :tooltip="$t('common.openDocs')" @click="openDoc">
        <template #icon>
          <n-icon :size="18">
            <icon-ion-book-outline />
          </n-icon>
        </template>
        <template v-if="!appStore.siderCollapse">
          {{ $t("common.docsFull") }}
        </template>
      </tooltip-button>
      <n-popover trigger="click" placement="top" :show-arrow="false">
        <template #trigger>
          <div class="w-full">
            <tooltip-button quaternary block :tooltip="$t('page.hub.dashboard.settings')">
              <template #icon>
                <n-icon :size="18">
                  <icon-ion-settings-outline />
                </n-icon>
              </template>
              <template v-if="!appStore.siderCollapse">
                {{ $t("page.hub.dashboard.settings") }}
              </template>
            </tooltip-button>
          </div>
        </template>
        <div class="chat-menu__popover">
          <div class="chat-menu__popover-title">
            {{ $t("page.hub.dashboard.settings") }}
          </div>
          <n-button
            text
            size="small"
            class="chat-menu__popover-item chat-menu__popover-item--danger"
            @click="handleClearHistory"
          >
            <n-icon :size="14">
              <icon-ion-trash-outline />
            </n-icon>
            <span>{{ `${$t("chat.common.clear")} ${$t("chat.history")}` }}</span>
          </n-button>
        </div>
      </n-popover>
      <tooltip-button
        quaternary
        block
        :tooltip="appStore.siderCollapse ? $t('icon.expand') : $t('icon.collapse')"
        @click="appStore.toggleSiderCollapse"
      >
        <template #icon>
          <n-icon>
            <icon-ion-chevron-back v-if="!appStore.siderCollapse" />
            <icon-ion-chevron-forward v-else />
          </n-icon>
        </template>
        <span v-if="!appStore.siderCollapse">{{ $t("icon.collapse") }}</span>
      </tooltip-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAppStore } from "@/store/modules/app"
import { TooltipButton } from "@airalogy/components"
import { useOrProvideChatInfoStore } from "@airalogy/components/chat/composables/useChatInfoStore"
import { $t } from "@airalogy/shared/locales"
import { useDialog } from "naive-ui"
import { nanoid } from "nanoid"
import { useOpenNewTab } from "../../composables"
import ChatHistorySidebar from "./chat-history-sidebar.vue"

defineOptions({ name: "GlobalMenu" })

const appStore = useAppStore()
const dialog = useDialog()

const { handleAddNewSession, clearHistory } = useOrProvideChatInfoStore({}, () => ({}))

// Handle new chat creation
function handleNewChat() {
  const newChatId = nanoid()

  // Create empty session
  handleAddNewSession(newChatId, "global")
}

const { openNewTab } = useOpenNewTab()

function openDoc() {
  window.open(import.meta.env.VITE_DOCS_URL || "https://github.com/airalogy/platform/tree/main/docs", "_blank")
}

function handleClearHistory() {
  dialog.warning({
    title: `${$t("chat.common.clear")} ${$t("chat.history")}`,
    content: $t("chat.clearHistoryConfirm"),
    positiveText: $t("common.confirm"),
    negativeText: $t("common.cancel"),
    closable: true,
    onPositiveClick: () => clearHistory(),
  })
}
</script>

<style scoped lang="sass">
.global-menu
  @apply p-2

  &__label
    @apply font-medium text-gray-700

.chat-menu__popover
  padding: 8px 6px
  min-width: 180px

.chat-menu__popover-title
  @apply px-2 pb-1 text-xs text-gray-500

.chat-menu__popover-item
  @apply w-full justify-start gap-2 rounded-md px-2 py-1 text-sm

  &:hover
    @apply bg-gray-100

.chat-menu__popover-item--danger
  @apply text-red-500

  &:hover
    @apply bg-red-50
</style>

<template>
  <div :class="containerClass">
    <!-- Desktop view: shown on larger screens -->
    <div class="actions-row">
      <tooltip-button
        v-if="!collapsed && !hideCollapse"
        :button-props="{ quaternary: true }"
        :tooltip="collapsed ? $t('chat.expand') : $t('chat.collapse')"
        :icon-props="{ size: 18 }"
        @click="$emit('toggleCollapse')"
      >
        <template #icon>
          <icon-shared-menu-expand />
        </template>
      </tooltip-button>

      <template v-for="(action, index) in actionButtons" :key="`action-${index}`">
        <tooltip-button
          :button-props="{ quaternary: true }"
          :tooltip="action.tooltip"
          :icon="action.icon"
          :icon-props="{ size: action.iconSize || 18 }"
          @click="action.handler"
        />
      </template>

      <chat-history />
    </div>

    <!-- Mobile view: shown on smaller screens -->
    <div class="actions-dropdown">
      <n-dropdown trigger="click" :options="dropdownOptions" @select="handleDropdownSelect">
        <n-button quaternary>
          <template #icon>
            <n-icon><icon-shared-menu-expand /></n-icon>
          </template>
        </n-button>
      </n-dropdown>
      <chat-history />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DropdownOption } from "naive-ui"
import DockExitIcon from "~icons/bx/dock-left"
import DockIcon from "~icons/bxs/dock-left"
import AddIcon from "~icons/ion/add"
import FullScreenIcon from "~icons/ion/arrow-expand"
import FullScreenExitIcon from "~icons/ion/arrow-shrink"
import { computed, h } from "vue"
import { $t } from "@airalogy/shared/locales"
import ChatHistory from "./chat-history.vue"

const props = withDefaults(defineProps<{
  fullScreen: boolean
  docked: boolean
  collapsed: boolean
  hideCollapse: boolean
  containerClass?: string | string[]
  actions?: string[]
}>(), {
  actions: () => ["dock", "fullscreen", "newChat"],
})

const emits = defineEmits<{
  (e: "toggleCollapse"): void
  (e: "toggleDock"): void
  (e: "toggleFullscreen"): void
  (e: "newChat"): void
}>()

// Define action buttons with their properties
const actionButtons = computed(() => [
  {
    id: "dock",
    tooltip: $t("chat.dock"),
    icon: props.docked ? DockExitIcon : DockIcon,
    event: "toggleDock",
    handler: () => emits("toggleDock"),
  },
  {
    id: "fullscreen",
    tooltip: $t("chat.fullScreen"),
    icon: props.fullScreen ? FullScreenExitIcon : FullScreenIcon,
    event: "toggleFullscreen",
    handler: () => emits("toggleFullscreen"),
  },
  {
    id: "newChat",
    tooltip: $t("chat.newChatButton"),
    icon: AddIcon,
    iconSize: 20,
    event: "newChat",
    handler: () => emits("newChat"),
  },
].filter(({ id }) => props.actions.includes(id)))

// Dropdown options for mobile view
const dropdownOptions = computed<DropdownOption[]>(() => [
  {
    key: "toggleDock",
    label: $t("chat.dock"),
    icon: () => h(props.docked ? DockExitIcon : DockIcon),
  },
  {
    key: "toggleFullscreen",
    label: $t("chat.fullScreen"),
    icon: () => h(props.fullScreen ? FullScreenExitIcon : FullScreenIcon),
  },
  {
    key: "newChat",
    label: $t("chat.newChatButton"),
    icon: () => h(AddIcon),
  },
])

// Handle dropdown selection
function handleDropdownSelect(key: string) {
  switch (key) {
    case "toggleDock":
      emits("toggleDock")
      break
    case "toggleFullscreen":
      emits("toggleFullscreen")
      break
    case "newChat":
      emits("newChat")
      break
  }
}
</script>

<style lang="sass" scoped>
.actions-row
  display: flex
  align-items: center

.actions-dropdown
  display: none
  align-items: center

// Media query to switch between normal buttons and dropdown
@media (max-width: 640px)
  .actions-row
    display: none

  .actions-dropdown
    display: flex
</style>

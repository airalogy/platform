<template>
  <div class="flex items-center gap-1">
    <!-- Thinking Toggle -->
    <tooltip-button
      :icon="BrainIcon"
      :tooltip="enableThinking ? $t('chat.thinkingEnabled') : $t('chat.enableThinking')"
      :button-props="{
        quaternary: true,
        type: enableThinking ? 'primary' : 'default',
        size: 'small',
        themeOverrides: {
          heightSmall: 'fit-content',
          paddingSmall: '8px',
          borderRadiusSmall: '8px',
        },
      }"
      :icon-props="{ size: 20, class: 'thin-icon' }"
      :disabled="isRecording"
      @click="handleToggleThinking"
    />

    <!-- Search Toggle -->
    <tooltip-button
      :icon="SearchIcon"
      :tooltip="enableSearch ? $t('chat.searchEnabled') : $t('chat.enableSearch')"
      :button-props="{
        quaternary: true,
        type: enableSearch ? 'primary' : 'default',
        size: 'small',
        themeOverrides: {
          heightSmall: 'fit-content',
          paddingSmall: '8px',
          borderRadiusSmall: '8px',
        },
      }"
      :icon-props="{ size: 20, class: 'thin-icon' }"
      :disabled="isRecording"
      @click="handleToggleSearch"
    />

    <!-- Hub Search Toggle -->
    <tooltip-button
      :icon="HubIcon"
      :tooltip="enableHubSearch ? $t('chat.hubSearchEnabled') : $t('chat.enableHubSearch')"
      :button-props="{
        quaternary: true,
        type: enableHubSearch ? 'primary' : 'default',
        size: 'small',
        themeOverrides: {
          heightSmall: 'fit-content',
          paddingSmall: '8px',
          borderRadiusSmall: '8px',
        },
      }"
      :icon-props="{ size: 20, class: 'thin-icon' }"
      :disabled="isRecording"
      @click="handleToggleHubSearch"
    />
  </div>
</template>

<script setup lang="ts">
import BrainIcon from "~icons/tabler/bulb"
import HubIcon from "~icons/tabler/compass"
import SearchIcon from "~icons/tabler/world"
import { $t } from "@airalogy/shared/locales"
import { useChatInfoStore } from "../../composables/useChatInfoStore"

const { enableThinking, enableSearch, enableHubSearch, isRecording } = useChatInfoStore()!

function handleToggleThinking() {
  enableThinking.value = !enableThinking.value
}

function handleToggleSearch() {
  enableSearch.value = !enableSearch.value
}

function handleToggleHubSearch() {
  enableHubSearch.value = !enableHubSearch.value
}
</script>

<style>
.thin-icon svg {
  color: currentColor;
}
.thin-icon svg * {
  stroke-width: 1.5 !important;
}
</style>

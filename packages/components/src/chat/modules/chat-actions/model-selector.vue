<template>
  <n-dropdown trigger="click" placement="bottom-start" :options="dropdownOptions" @select="handleSelect">
    <div class="inline-flex">
      <n-button
        ghost :bordered="false" :class="buttonClass" :disabled="isRecording" :size="buttonSize"
        icon-placement="right"
        v-bind="buttonProps"
      >
        <component :is="modelIcon" v-if="modelIcon" class="mr-1" />
        <span>{{ modelName }}</span>
        <template #icon>
          <n-icon :size="iconSize" v-bind="iconProps">
            <icon-ion-ios-arrow-down />
          </n-icon>
        </template>
      </n-button>
    </div>
  </n-dropdown>
</template>

<script setup lang="ts">
import type { ChatModel } from "@airalogy/shared/enum"
import type { ButtonProps, DropdownOption, IconProps, SelectOption } from "naive-ui"
import { $t } from "@airalogy/shared/locales"
import { useChatInfoStore } from "../../composables/useChatInfoStore"

const props = withDefaults(defineProps<{
  buttonClass?: string
  buttonSize?: "tiny" | "small" | "medium" | "large"
  iconSize?: number
  buttonProps?: Partial<ButtonProps>
  iconProps?: Partial<IconProps>
}>(), {
  buttonClass: "h-8 w-fit",
  buttonSize: "small",
  iconSize: 14,
})

const { selectedModel, modelName, isRecording, modelOptions } = useChatInfoStore()!

const modelIcon = computed(() => {
  return modelOptions.value.find(option => option.value === selectedModel.value)?.icon
})

const dropdownOptions = computed<DropdownOption[]>(() => ([
  {
    type: "group",
    key: "model-group",
    label: $t("chat.model.select"),
    children: modelOptions.value as DropdownOption[],
  },
]))

function handleSelect(_: unknown, option: SelectOption) {
  selectedModel.value = option.value as ChatModel
}
</script>

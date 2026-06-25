<template>
  <define-id-input>
    <n-input
      v-model:value="inputValue"
      type="text"
      :maxlength="40"
      required
      show-count
      autosize
      :placeholder="props.placeholder || defaultPlaceholder"
      :disabled="props.inputProps?.disabled || disabled"
      class="w-full"
      v-bind="props.inputProps"
      @update:value="handleUpdateValue"
      @keydown.enter="handleCheck"
    >
      <template #prefix>
        <div v-if="showPrefix" class="w-full whitespace-pre-wrap pl-1 text-3.5 color-text-secondary">
          {{ computedPrefix }}
        </div>
      </template>
      <template #suffix>
        <n-button
          type="primary"
          class="order-last ml-4"
          size="small"
          :loading="checkLoading"
          :disabled="checkLoading || disabled"
          @click="handleCheck"
        >
          {{ $t("common.idInput.check") }}
        </n-button>
      </template>
    </n-input>
  </define-id-input>

  <n-tooltip ref="tooltipRef" :trigger="props.trigger" :placement="props.placement" class="max-w-70%">
    <template #trigger>
      <div v-if="$slots.default" class="size-full flex items-center justify-center">
        <id-input />
        <slot />
      </div>
      <id-input v-else />
    </template>
    {{ props.tooltip || defaultTooltip }}
  </n-tooltip>
</template>

<script setup lang="ts">
import type { InputProps, TooltipInst } from "naive-ui"
import { $t } from "@airalogy/shared/locales"
import { computed, ref } from "vue"

type IdType = "lab" | "project" | "protocol" | "hub" | "group" | "protocol"

interface Props {
  modelValue?: string | null
  type: IdType
  labUid?: string
  projectUid?: string
  protocolUid?: string
  protocolId?: number
  showPrefix?: boolean
  disabled?: boolean
  placeholder?: string
  tooltip?: string
  checkLoading?: boolean
  size?: "small" | "medium" | "large"
  trigger?: "focus" | "hover"
  placement?: "top" | "top-start" | "top-end" | "bottom" | "bottom-start" | "bottom-end" | "left" | "left-start" | "left-end" | "right" | "right-start" | "right-end"
  inputProps?: InputProps & { class?: string }
}

const props = withDefaults(defineProps<Props>(), {
  labUid: "",
  projectUid: "",
  showPrefix: false,
  disabled: false,
  placeholder: "",
  tooltip: "",
  checkLoading: false,
  size: "medium",
  trigger: "focus",
  placement: "top-start",
})

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void
  (e: "check", value: string): void
  (e: "update:value", value: string): void
}>()

const [DefineIdInput, IdInput] = createReusableTemplate()

const inputValue = computed({
  get: () => props.modelValue || "",
  set: value => emit("update:modelValue", value),
})

const computedPrefix = computed(() => {
  const origin = window.location.origin

  switch (props.type) {
    case "lab":
      return `${origin}/labs/`
    case "group":
      if (!props.labUid)
        return ""
      return `${origin}/labs/${props.labUid}/groups/`
    case "project":
      if (!props.labUid)
        return ""
      return `${origin}/labs/${props.labUid}/projects/`
    case "protocol":
      if (!props.labUid || !props.projectUid)
        return ""
      return `${origin}/labs/${props.labUid}/projects/${props.projectUid}/protocols/`
    case "hub":
      return `${origin}/hub/${props.labUid}.${props.projectUid}.${props.protocolUid}.`
    default:
      return ""
  }
})

const defaultPlaceholder = computed(() => {
  switch (props.type) {
    case "lab":
      return $t("common.idInput.placeholder.lab")
    case "group":
      if (!props.labUid)
        return ""
      return $t("common.idInput.placeholder.group")
    case "project":
      return $t("common.idInput.placeholder.project")
    case "protocol":
      return $t("common.idInput.placeholder.protocol")
    case "hub":
      return $t("common.idInput.placeholder.hub")
    default:
      return $t("common.idInput.placeholder.default")
  }
})

const defaultTooltip = computed(() => {
  switch (props.type) {
    case "lab":
      return $t("common.idInput.tooltip.lab")
    case "project":
      return $t("common.idInput.tooltip.project")
    case "protocol":
      return $t("common.idInput.tooltip.protocol")
    case "hub":
      return $t("common.idInput.tooltip.hub")
    default:
      return $t("common.idInput.tooltip.default")
  }
})

function handleUpdateValue(value: string) {
  emit("update:value", value)
}

function handleCheck() {
  emit("check", inputValue.value)
}

const tooltipRef = ref<TooltipInst | null>(null)
</script>

<style scoped lang="sass">
:deep(.n-input__prefix)
  max-width: 100%
:deep(.n-input-wrapper)
  flex-wrap: wrap
:deep(.n-input__suffix)
  margin-left: auto
</style>

<template>
  <define-version-input>
    <div class="semver-container flex flex-wrap items-center">
      <n-input-number
        ref="majorInputRef"
        v-model:value="majorVersion"
        :min="0"
        :max="999"
        placeholder="0"
        :disabled="props.inputProps?.disabled || disabled"
        class="semver-input"
        size="small"
        :theme-overrides="props.themeOverrides"
        @update:value="handleUpdatePart"
      />
      <span class="mx-1 text-gray-500">.</span>
      <n-input-number
        ref="minorInputRef"
        v-model:value="minorVersion"
        :min="0"
        :max="999"
        placeholder="0"
        :disabled="props.inputProps?.disabled || disabled"
        class="semver-input"
        size="small"
        :theme-overrides="props.themeOverrides"
        @update:value="handleUpdatePart"
      />
      <span class="mx-1 text-gray-500">.</span>
      <n-input-number
        ref="patchInputRef"
        v-model:value="patchVersion"
        :min="0"
        :max="999"
        placeholder="1"
        :disabled="props.inputProps?.disabled || disabled"
        class="semver-input"
        size="small"
        :theme-overrides="props.themeOverrides"
        @update:value="handleUpdatePart"
      />
      <div v-if="!isValidVersion && (majorVersion != null || minorVersion != null || patchVersion != null)" class="ml-2 flex items-center text-red-500">
        <n-icon size="16">
          <icon-ion-alert-circle />
        </n-icon>
      </div>
      <n-button
        v-if="props.showCheckButton"
        type="primary"
        class="order-last ml-4"
        size="small"
        :loading="checkLoading"
        :disabled="checkLoading || disabled || !isValidVersion"
        @click="handleCheck"
      >
        Check
      </n-button>
    </div>
  </define-version-input>

  <n-tooltip ref="tooltipRef" :trigger="props.trigger" :placement="props.placement" class="max-w-70%">
    <template #trigger>
      <div v-if="$slots.default" class="size-full flex items-center">
        <version-input />
        <slot />
      </div>
      <version-input v-else />
    </template>
    {{ props.tooltip || defaultTooltip }}
  </n-tooltip>
</template>

<script setup lang="ts">
import type { InputNumberProps, InputProps, TooltipInst } from "naive-ui"
import { useSyncInputMirror } from "@airalogy/composables"
import IconIonAlertCircle from "~icons/ion/alert-circle"
import { computed, onMounted, ref, watch } from "vue"

interface Props {
  modelValue?: string | null
  disabled?: boolean
  placeholder?: string
  tooltip?: string
  checkLoading?: boolean
  size?: "small" | "medium" | "large"
  trigger?: "focus" | "hover"
  placement?: "top" | "top-start" | "top-end" | "bottom" | "bottom-start" | "bottom-end" | "left" | "left-start" | "left-end" | "right" | "right-start" | "right-end"
  inputProps?: InputProps
  showCheckButton?: boolean
  themeOverrides?: InputNumberProps["themeOverrides"]
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  placeholder: "",
  tooltip: "",
  checkLoading: false,
  size: "medium",
  trigger: "focus",
  placement: "top-start",
  showCheckButton: false,
  themeOverrides: () => ({
    peers: {
      Input: {
        heightSmall: "40px",
      },
    },
  }),
})

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void
  (e: "check", value: string): void
  (e: "update:value", value: string): void
  (e: "validate", isValid: boolean): void
}>()

const [DefineVersionInput, VersionInput] = createReusableTemplate()

// Separate version parts
const majorVersion = ref<number | undefined >(undefined)
const minorVersion = ref<number | undefined>(undefined)
const patchVersion = ref<number | undefined>(undefined)

// Input refs for mirror sync
const majorInputRef = ref<any>(undefined)
const minorInputRef = ref<any>(undefined)
const patchInputRef = ref<any>(undefined)

// Mirror sync state
const majorSyncKey = ref("value")
const minorSyncKey = ref("value")
const patchSyncKey = ref("value")
const shouldSyncMajor = ref(false)
const shouldSyncMinor = ref(false)
const shouldSyncPatch = ref(false)

// Combined version value
const combinedVersion = computed(() => {
  if (typeof majorVersion.value === "undefined" && typeof minorVersion.value === "undefined" && typeof patchVersion.value === "undefined") {
    return ""
  }

  const major = typeof majorVersion.value === "undefined" ? 0 : majorVersion.value
  const minor = typeof minorVersion.value === "undefined" ? 0 : minorVersion.value
  const patch = typeof patchVersion.value === "undefined" ? 0 : patchVersion.value

  return `${major}.${minor}.${patch}`
})

// Watch for external value changes
watch(() => props.modelValue, (newValue) => {
  if (newValue) {
    const parts = newValue.split(".")
    majorVersion.value = parts[0] ? Number.parseInt(parts[0], 10) : undefined
    minorVersion.value = parts[1] ? Number.parseInt(parts[1], 10) : undefined
    patchVersion.value = parts[2] ? Number.parseInt(parts[2], 10) : undefined
  }
  else {
    majorVersion.value = undefined
    minorVersion.value = undefined
    patchVersion.value = undefined
  }
}, { immediate: true })

// Watch for internal value changes to emit updates
watch(combinedVersion, (newValue) => {
  emit("update:modelValue", newValue)
  emit("update:value", newValue)
  validateVersion(newValue)
})

// Setup mirror sync for each input
onMounted(() => {
  // Setup mirror sync for major version input
  useSyncInputMirror(
    majorInputRef,
    {
      value: majorVersion.value?.toString() || "0",
      type: "text",
      placeholder: "0",
    },
    majorSyncKey,
    shouldSyncMajor,
  )

  // Setup mirror sync for minor version input
  useSyncInputMirror(
    minorInputRef,
    {
      value: minorVersion.value?.toString() || "0",
      type: "text",
      placeholder: "0",
    },
    minorSyncKey,
    shouldSyncMinor,
  )

  // Setup mirror sync for patch version input
  useSyncInputMirror(
    patchInputRef,
    {
      value: patchVersion.value?.toString() || "1",
      type: "text",
      placeholder: "1",
    },
    patchSyncKey,
    shouldSyncPatch,
  )
})

const defaultTooltip = computed(() => {
  return "Protocol version in semantic versioning format (x.y.z). Default is 0.0.1."
})

const isValidVersion = ref(true)

function validateVersion(version: string): boolean {
  if (!version) {
    isValidVersion.value = true
    emit("validate", true)
    return true
  }

  // All numeric values are valid in this input approach
  const isValid = true
  isValidVersion.value = isValid
  emit("validate", isValid)
  return isValid
}

function handleUpdatePart() {
  // The combined version computed property will handle the updates
}

function handleCheck() {
  emit("check", combinedVersion.value)
}

const tooltipRef = ref<TooltipInst | null>(null)
onMounted(() => {
  if (!props.modelValue) {
    majorVersion.value = 0
    minorVersion.value = 0
    patchVersion.value = 1
  }
})
</script>

<style scoped lang="sass">
:deep(.n-input__input-mirror)
  margin-right: 10px
</style>

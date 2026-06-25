<template>
  <n-input
    v-bind="$attrs"
    ref="inputRef"
    v-model:value="displayValue"
    :size="props.size"
    :theme-overrides="props.themeOverrides"
    :placeholder="props.placeholder"
    :disabled="props.disabled"
    :status="props.status"
    readonly
    autosize
    class="custom-record-id-input"
    @click="openDialog"
    @focus="handleFocus"
    @blur="handleBlur"
  >
    <!-- Explicitly forward known slots -->
    <template v-if="$slots.prefix" #prefix>
      <slot name="prefix" />
    </template>
    <template v-if="!props.disabled || $slots.suffix" #suffix>
      <div class="record-id-input__suffix">
        <slot name="suffix" />
        <n-button v-if="!props.disabled" quaternary size="small" class="w-6 -mr-1.5" @click.stop="openDialog">
          <template #icon>
            <n-icon :size="14">
              <icon-ion-search />
            </n-icon>
          </template>
        </n-button>
      </div>
    </template>
  </n-input>

  <!-- Use the context-select-dialog component with single selection mode -->
  <context-select-dialog
    v-model:show="isDialogOpen"
    v-model:selected="selectedRecordIds"
    type="record"
    source="protocol"
    :options="[]"
    :default-selected-path="defaultSelectedPath"
    dry
    :default-selected-options="defaultSelectedOptions"
    @confirm="handleConfirm"
  />
</template>

<script setup lang="ts">
import ContextSelectDialog from "@/components/chat/modules/context-select-dialog.vue"
import { useSyncInputMirror } from "@airalogy/composables"
import { useVModel } from "@vueuse/core"
import { NButton, NIcon, NInput } from "naive-ui"
import { computed, ref, watch } from "vue"
import { useProtocolInfoStore } from "../../views/project-protocols/hooks/useProtocolInfoStore"

defineOptions({
  name: "CustomRecordIdInput",
  inheritAttrs: false,
})

const props = withDefaults(defineProps<IProps>(), {
  value: null,
  disabled: false,
  placeholder: "Click to select a record",
  recordType: "default",
})

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "update:value", value: string | null): void
  (e: "blur"): void
  (e: "focus"): void
  (e: "update:multiple-value", value: any[]): void
  (e: "change", value: string): void
}
export interface IProps {
  value?: string | null
  disabled?: boolean
  placeholder?: string
  status?: "success" | "warning" | "error" | undefined
  loading?: boolean
  // Optional filtering parameters
  recordType?: string
  filter?: Record<string, any>
  themeOverrides?: any
  size?: "large" | "medium" | "small" | "tiny"
  autosize?: boolean
}

// State
const isDialogOpen = ref(false)

const displayValue = useVModel(props, "value", emit)
const { protocolInfo } = useProtocolInfoStore()!

const defaultSelectedPath = computed(() => {
  if (!protocolInfo?.value)
    return undefined

  const { lab, project, id } = protocolInfo.value

  return `${lab.id}_${project.id}_${id}`
})

const defaultSelectedOptions = computed(() => {
  if (!protocolInfo?.value) {
    return []
  }

  const { lab, project, id, name } = protocolInfo.value

  const protocolNode = {
    label: name,
    value: `${lab.id}_${project.id}_${id}`,
    depth: 3,
    isLeaf: true,
  }

  const projectNode = {
    label: project.name,
    value: `${lab.id}_${project.id}`,
    depth: 2,
    isLeaf: false,
    uid: project.uid,
    children: [protocolNode],
  }

  const labNode = {
    label: lab.name,
    value: lab.id,
    depth: 1,
    isLeaf: false,
    uid: lab.uid,
    children: [projectNode],
  }

  return [labNode]
})

const selectedRecordIds = ref<string[]>([])

// Input reference
const inputRef = ref<InstanceType<typeof NInput> | null>(null)
const syncValueKey = ref("value")
const shouldSyncValueToMirror = ref(false)

// Set up input mirror sync
useSyncInputMirror(inputRef, props, syncValueKey, shouldSyncValueToMirror)

// Open the record selection dialog
function openDialog() {
  if (props.disabled)
    return

  isDialogOpen.value = true
}

function handleFocus() {
  emit("focus")
}

function handleBlur() {
  if (!isDialogOpen.value) {
    emit("blur")
  }
}

watch(isDialogOpen, (show, prevShow) => {
  if (!show) {
    selectedRecordIds.value = []
    if (prevShow) {
      emit("blur")
    }
  }
})

// Handle selection confirmation from context dialog
function handleConfirm(selectedItems: (Chat.ChatContext)[]) {
  if (selectedItems.length === 0) {
    return
  }
  if (selectedItems.length === 1) {
    const { airalogyId } = selectedItems[0]
    displayValue.value = airalogyId
    emit("change", airalogyId)
  }
  else {
    emit("update:multiple-value", selectedItems.map(item => item.airalogyId))
  }
}

defineExpose({ inputRef })
</script>

<style scoped lang="sass">
.custom-record-id-input
  :deep(.n-input-wrapper)
    cursor: pointer

.record-id-input__suffix
  display: flex
  align-items: center
  gap: 4px
</style>

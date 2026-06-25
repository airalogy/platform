<template>
  <div class="horizontal-dynamic-input">
    <!-- Input items displayed horizontally -->
    <div
      v-for="(_, index) in items"
      :key="index"
      class="dynamic-input-item"
    >
      <!-- Index indicator (starting from 1) -->
      <div class="mx-1">
        {{ index + 1 }}.
      </div>

      <!-- Input field -->
      <component
        :is="props.inputComponent"
        :ref="(el: any) => handleSyncValueToMirror(el, index)"
        v-model:value="items[index]"
        size="small"
        autosize
        :disabled="props.disabled"
        :placeholder="props.placeholder"
        :theme-overrides="props.themeOverrides"
        @change="emit('update:value', items)"
        @update:multiple-value="(val: any[]) => handleMultipleChange(index, val)"
      >
        <template v-if="!props.disabled" #prefix>
          <n-button type="error" size="small" class="h-full w-6 -ml-1 !p-0" quaternary @click="removeItem(index)">
            <template #icon>
              <n-icon :size="16">
                <icon-material-symbols-delete-outline />
              </n-icon>
            </template>
          </n-button>
        </template>
      </component>
    </div>

    <!-- Add button at the bottom -->
    <n-button v-if="!props.disabled" type="primary" size="small" class="flex-1 rounded-md" ghost @click="addItem">
      <template #icon>
        <icon-material-symbols-add-circle-outline />
      </template>
      {{ addButtonText || 'Add Item' }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import type { Component, WatchStopHandle } from "vue"
import IconMaterialSymbolsAddCircleOutline from "~icons/material-symbols/add-circle-outline"
import IconMaterialSymbolsDeleteOutline from "~icons/material-symbols/delete-outline"
import { isEqual } from "lodash-es"
import { NButton, NInput } from "naive-ui"

interface IProps {
  placeholder?: string
  addButtonText?: string
  value?: string[]
  inputComponent?: Component
  themeOverrides?: any
  disabled?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  inputComponent: () => NInput,
})

const emit = defineEmits<IEmits>()

interface IEmits {
  (e: "update:value", value: string[]): void
}

// Local state for the input items
const items = ref<string[]>(props.value || [])

// Method to add a new item
function addItem() {
  items.value.push("")
}

const refs = ref<any[]>([])

function handleSyncValueToMirror(el: any, index: number) {
  if (el) {
    refs.value[index] = el
  }
}

// Handle change for a specific item
function handleMultipleChange(index: number, value: any[]) {
  items.value.splice(index, 1, ...value)
  emit("update:value", items.value)
}

watch(refs, (value) => {
  value.forEach(async (el, index) => {
    const stop: WatchStopHandle[] = []

    stop.push(watch(() => el?.inputMirrorElRef, (mirror) => {
      if (!mirror) {
        stop.forEach(s => s())
        return
      }

      stop.push(watch(() => items.value[index], (value) => {
        if (value) {
          mirror.textContent = value
        }
        else {
          mirror.innerHTML = props.placeholder || "&nbsp;"
        }
      }, { immediate: true, flush: "post" }))
    }))
  })
}, { deep: true })

// Watch for external changes to the model
watch(() => props?.value, (newValue) => {
  if (Array.isArray(newValue)) {
    if (!isEqual(newValue, items.value)) {
      items.value = [...newValue]
    }
  }
}, { deep: true, immediate: true })

// Method to remove an item
function removeItem(index: number) {
  if (items.value.length) {
    items.value.splice(index, 1)
    emit("update:value", items.value)
  }
}
</script>

<style scoped lang="sass">
.horizontal-dynamic-input
  display: flex
  flex-direction: row
  align-items: center
  gap: 3px
  width: fit-content
  min-width: 100%
  max-width: 100%
  flex-wrap: wrap

.dynamic-input-item
  display: flex
  align-items: center
  max-width: 100%

.input-field-wrapper
  flex: 1
  margin-right: 12px

.add-button-container
  display: flex
  justify-content: center
  margin-top: 8px

:deep(.n-input)
  max-width: min(calc(100% - 30px), fit-content)
  min-width: 100px
:deep(.n-input-wrapper)
  padding: 2px 8px 2px 6px!important
</style>

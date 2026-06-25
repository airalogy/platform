<template>
  <div class="editor__breadcrumbs" :class="{ hidden: isHidden }">
    <n-scrollbar x-scrollable class="!overflow-visible">
      <n-breadcrumb
        class="size-full"
        :theme-overrides="{
          itemTextColor: '#00000088',
          itemTextColorActive: '#000000',
          separatorColor: '#00000088',
        }"
      >
        <n-breadcrumb-item v-for="(item, index) in breadcrumbItems" :key="index">
          <n-dropdown
            :value="item.path"
            :options="item.options || []"
            :disabled="!item.options?.length"
            trigger="click"
            size="small"
            :theme-overrides="{
              optionHeightSmall: '20px',
              fontSizeSmall: '12px',
              optionTextColor: '#00000088',
              optionTextColorHover: '#000000',
              optionTextColorActive: '#000000',
            }"
            @select="(key: string | number) => handleSelect(key, item)"
          >
            <div class="flex cursor-pointer items-center">
              <n-icon
                v-if="item.icon"
                :component="item.icon"
                :size="12"
                class="vertical-middle text-black/60"
              />
              <span
                class="ml-1 vertical-middle text-xs text-black/90"
              >
                {{ item.label }}
              </span>
            </div>
          </n-dropdown>
          <template #separator>
            <n-icon size="12" class="text-black/60">
              <icon-ion-ios-arrow-forward />
            </n-icon>
          </template>
        </n-breadcrumb-item>
      </n-breadcrumb>
    </n-scrollbar>
  </div>
</template>

<script setup lang="ts">
import type { DropdownOption } from "naive-ui"
import type { Component, Raw } from "vue"
import { useThemeStore } from "@airalogy/composables/theme"
import { getFileSpecificIcon } from "@airalogy/shared/utils"
import FolderIcon from "~icons/tabler/folder"
import { NBreadcrumb, NBreadcrumbItem, NDropdown, NIcon } from "naive-ui"
import { computed, ref } from "vue"
import { type DiffModelInfo, type ModelInfo, useModelsStore } from "./store/editorStore"

export interface BreadcrumbItem {
  label: string
  icon?: Component
  options?: DropdownOption[]
  path?: string
}

const props = defineProps<IProps>()

const emit = defineEmits<{
  (e: "select", key: string | number, item: BreadcrumbItem): void
}>()

interface IProps {
  editorId: number
  loadOptions?: (path: string) => DropdownOption[]
}

const modelsStore = useModelsStore()
const { getActiveModelInfo } = modelsStore
const isHidden = ref(false)

const currentModel = shallowRef<Raw<ModelInfo | DiffModelInfo> | null>(null)

const currentPath = computed(() => currentModel.value?.path || "")

const breadcrumbItems = computed<BreadcrumbItem[]>(() => {
  if (!currentPath.value) {
    return []
  }

  const pathParts = currentPath.value.split("/")
  return pathParts.map((part, index) => {
    const isFile = index === pathParts.length - 1
    const path = pathParts.slice(0, index + 1).join("/")

    return {
      label: part === "." ? "" : part || "/",
      icon: isFile ? getFileSpecificIcon(part) : FolderIcon,
      path,
      options: getOptionsForPath(path), // Will be populated when dropdown is clicked
    }
  })
})

// Function to load options for a breadcrumb item
function loadItemOptions(path: string): DropdownOption[] {
  if (props.loadOptions) {
    return props.loadOptions(path)
  }
  return []
}

// This will store cached options for paths
const optionsCache = ref<Record<string, DropdownOption[]>>({})

// Function to get or load options for a path
function getOptionsForPath(path: string) {
  if (!optionsCache.value[path]) {
    optionsCache.value[path] = loadItemOptions(path)
  }
  return optionsCache.value[path]
}

function handleSelect(key: string | number, item: BreadcrumbItem) {
  emit("select", key, item)
}

// Public methods that match VSCode's implementation
function update() {
  // Trigger a re-render of breadcrumbs
  isHidden.value = false
}

function revealLast() {
  // Scroll to the last breadcrumb item if needed
  isHidden.value = false
}

const themeStore = useThemeStore()
// Dark mode has been removed from the project

watchEffect(() => {
  currentModel.value = getActiveModelInfo(props.editorId) || null
})

defineExpose({
  isHidden,
  update,
  revealLast,
})
</script>

<style lang="sass" scoped>
.editor__breadcrumbs
  @apply h-fit transition-colors duration-200
  :deep(.n-scrollbar-rail--horizontal)
    bottom: -4px!important

  :deep(.n-breadcrumb-item__separator)
    margin: 0 3px!important
</style>

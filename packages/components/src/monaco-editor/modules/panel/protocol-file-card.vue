<template>
  <n-card
    :bordered="true"
    :segmented="{ content: true }"
    :theme-overrides="{ paddingSmall: '6px 8px 6px 8px' }"
    size="small"
    header-extra-class="gap-2"
    :content-class="isCollapsed && !isAnimating ? 'diff-content diff-content-collapsed' : 'diff-content'"
    footer-class="flex gap-2 items-center !p-2"
  >
    <!-- Header: File name and path -->
    <template #header>
      <div class="flex cursor-pointer items-center" @click="handleToggleCollapsed">
        <n-icon :size="18" class="mr-2 transition" :class="{ '-rotate-90': isCollapsed }">
          <icon-ion-ios-arrow-down />
        </n-icon>
        <n-icon :component="getFileSpecificIcon(props.name)" :size="18" class="mr-2" />
        <n-ellipsis class="font-medium">
          {{ props.name }}
        </n-ellipsis>

        <n-tag v-if="!isExist" type="success" size="small" class="ml-2">
          New
        </n-tag>
        <n-tag v-else-if="isUpdated" type="warning" size="small" class="ml-2">
          Conflict
        </n-tag>
      </div>
    </template>

    <!-- Header extra: Action buttons -->
    <template #header-extra>
      <tooltip-button v-for="(action, idx) in actions" :key="idx" :tooltip="action.tooltip" :button-props="{ size: 'tiny', quaternary: true }" :icon="action.icon" @click.stop="action.handler" />
    </template>

    <n-collapse-transition :show="!isCollapsed" @leave="startAnimation" @after-leave="stopAnimation">
      <template v-if="diffContent && props.status !== 'success'">
        <pre
          v-for="(part, index) in diffContent" :key="index"
          :class="part.added ? 'added' : part.removed ? 'removed' : 'unchanged'"
        >
        <code>{{ part.value }}</code>
      </pre>
      </template>
      <shiki-code-viewer v-else-if="props.content" :code="props.content || ''" :language="getFileLanguage(props.name)" :use-wrapper="false" theme="github-light" />
      <n-empty v-else description="No content" class="flex-1" />
    </n-collapse-transition>

    <!-- Footer: Diff stats -->
    <template #footer>
      <n-button v-if="!isExist" type="primary" size="small" class="ml-auto" @click="saveChanges">
        Save
      </n-button>
      <template v-else-if="isUpdated">
        <span class="text-sm text-gray-500">
          {{ diffContent.length }} blocks changed
        </span>
        <span class="text-sm text-green-600">
          +{{ diffContent.filter(p => p.added).reduce((acc, p) => acc + (p.count || 0), 0) }}
        </span>
        <span class="text-sm text-red-500">
          -{{ diffContent.filter(p => p.removed).reduce((acc, p) => acc + (p.count || 0), 0) }}
        </span>
        <n-button size="small" type="primary" class="ml-auto" @click="applyChanges">
          Apply
        </n-button>
      </template>
    </template>
  </n-card>
</template>

<script setup lang="ts">
import shikiCodeViewer from "@airalogy/components/file-preview/code-preview/shiki-code-viewer.vue"
import { useBoolean } from "@airalogy/composables"
import { getFileLanguage, getFileSpecificIcon } from "@airalogy/shared/utils"
import PreviewIcon from "~icons/fluent/eye-show-12-regular"
import OpenOutline from "~icons/ion/open-outline"
import CodeDiffIcon from "~icons/ph/git-diff"
import { diffLines } from "diff"
import { NButton, NCard, NEllipsis, NIcon } from "naive-ui"

export interface IProps {
  name: string
  type: string
  path: string | null
  content: string | null
  sourcePath: string
  isExist: boolean
  isUpdated: boolean
  originalContent?: string | null // Original file content for diff
  status?: string
}

const props = withDefaults(defineProps<IProps>(), {
  originalContent: null,
})

const emit = defineEmits<IEmits>()

const { bool: isCollapsed, toggle: toggleCollapsed } = useBoolean(false)
const { bool: isAnimating, setTrue: startAnimation, setFalse: stopAnimation } = useBoolean(false)

interface IEmits {
  (e: "open"): void
  (e: "save"): void
  (e: "diff"): void
  (e: "showContent"): void
  (e: "apply"): void
  (e: "revert"): void
  (e: "fetchOriginal"): void
  (e: "update:isUpdated"): void
}

const { isExist } = toRefs(props)
const isUpdated = useVModel(props, "isUpdated", emit)

// Fetch or compute the original content when needed
const diffContent = computed(() => {
  return diffLines(props.originalContent || "", props.content || "")
})

watch(diffContent, (newDiff) => {
  if (newDiff.some(p => p.added || p.removed)) {
    isUpdated.value = true
  }
  else {
    isUpdated.value = false
  }
}, { immediate: true })

const actions = computed(() => {
  // Add file-specific actions based on the current state
  const baseActions: { tooltip: string, icon: any, handler: () => any }[] = [
    {
      tooltip: "Preview raw content",
      icon: PreviewIcon,
      handler: openDocument,
    },
  ]

  // Only add the open action if there's a path
  if (props.path) {
    baseActions.push({
      tooltip: "Open original file in editor",
      icon: OpenOutline,
      handler: openFile,
    })
  }

  // Add diff action if file exists and has updates
  if (isExist.value && isUpdated.value) {
    baseActions.push({
      tooltip: "Show diff between original and generated content",
      icon: CodeDiffIcon,
      handler: () => emit("diff"),
    })
  }

  return baseActions
})

function applyChanges() {
  emit("apply")
}

function revertChanges() {
  emit("revert")
}

function saveChanges() {
  emit("save")
}

async function openDocument() {
  emit("showContent")
}

async function openFile() {
  emit("open")
}
function handleToggleCollapsed() {
  toggleCollapsed()
}
</script>

<style scoped lang="sass">
:deep(.diff-content)
  @apply overflow-auto max-h-30 text-sm rounded border
  &.diff-content-collapsed
    border: 0
    padding: 0

  pre
    @apply p-1 m-0 whitespace-pre-wrap

    &.added
      @apply bg-green-50 text-green-800
      &::before
        content: "+"
        @apply mr-1 text-green-600

    &.removed
      @apply bg-red-50 text-red-800
      &::before
        content: "-"
        @apply mr-1 text-red-600

    &.unchanged
      @apply bg-white
</style>

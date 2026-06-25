<template>
  <n-list hoverable clickable>
    <template v-for="group in groupedProjectList" :key="group.parent.id">
      <n-list-item v-if="props.showPrivate || group.parent.type !== 1" class="group">
        <template #prefix>
          <project-icon />
        </template>
        <list-project-item :item="group.parent" :is-compact="false" class="min-w-0 flex-1" />
        <template #suffix>
          <div v-if="showPin || props.showActions" class="flex items-center gap-2">
            <edit-button v-if="props.showActions" :item="group.parent" type="lab" />
            <n-tooltip v-if="showPin" placement="top">
              <template #trigger>
                <n-button
                  quaternary
                  size="small"
                  class="pin-action"
                  :class="{ 'pin-action--active': isPinning(group.parent) }"
                  :loading="isPinning(group.parent)"
                  @click.stop="handleTogglePin(group.parent, $event)"
                >
                  <n-icon
                    :component="PinnedIcon"
                    :size="16"
                    :color="isPinned(group.parent) ? '#0084E2' : '#A1A4AF'"
                  />
                </n-button>
              </template>
              {{ isPinned(group.parent) ? $t("icon.unpin") : $t("icon.pin") }}
            </n-tooltip>
          </div>
        </template>
      </n-list-item>

      <div
        v-if="hasVisibleChildren(group.children) && (props.showPrivate || group.parent.type !== 1)"
        class="mb-4 ml-10 overflow-hidden border border-gray-200 rounded-lg bg-gray-50/60"
      >
        <div class="flex items-center justify-between border-b border-gray-200 px-4 py-2 text-xs text-gray-500 font-600">
          <span>{{ $t("page.project.settingsPage.subprojectsTitle") }}</span>
          <span>{{ getSubprojectCountLabel(group.children.length) }}</span>
        </div>
        <div class="divide-y divide-gray-100">
          <div
            v-for="child in visibleChildren(group.children)"
            :key="child.id"
            class="flex items-start gap-3 px-4 py-3"
          >
            <project-icon class="mt-1 shrink-0 opacity-70" />
            <list-project-item :item="child" :is-compact="false" class="min-w-0 flex-1" />
            <div v-if="showPin || props.showActions" class="flex items-center gap-2">
              <edit-button v-if="props.showActions" :item="child" type="lab" />
              <n-tooltip v-if="showPin" placement="top">
                <template #trigger>
                  <n-button
                    quaternary
                    size="small"
                    class="pin-action"
                    :class="{ 'pin-action--active': isPinning(child) }"
                    :loading="isPinning(child)"
                    @click.stop="handleTogglePin(child, $event)"
                  >
                    <n-icon
                      :component="PinnedIcon"
                      :size="16"
                      :color="isPinned(child) ? '#0084E2' : '#A1A4AF'"
                    />
                  </n-button>
                </template>
                {{ isPinned(child) ? $t("icon.unpin") : $t("icon.pin") }}
              </n-tooltip>
            </div>
          </div>
        </div>
      </div>
    </template>
  </n-list>
</template>

<script setup lang="ts">
import { type PinnedItem, PinnedResourceType } from "@/service/api/pinned-items"
import { $t } from "@airalogy/shared/locales"
import PinnedIcon from "~icons/tabler/pinned"

defineOptions({ name: "ProjectList" })

const props = withDefaults(defineProps<IProps>(), {
  list: () => [],
  showActions: false,
  showPrivate: true,
})

const emits = defineEmits<{
  (ev: "togglePin", payload: { resourceType: PinnedResourceType, resourceId: string }): void
}>()

interface IProps {
  list: Api.Project.MyProjectInfo[]
  showActions?: boolean
  showPrivate?: boolean
  pinnedMap?: Map<string, PinnedItem>
  pinningKeys?: Set<string>
}

const showPin = computed(() => Boolean(props.pinnedMap))
const groupedProjectList = computed(() => {
  const itemMap = new Map(props.list.map(item => [item.id, item]))
  const roots: Api.Project.MyProjectInfo[] = []
  const childrenMap = new Map<string, Api.Project.MyProjectInfo[]>()

  for (const item of props.list) {
    const parentId = item.parent_project_id
    if (!parentId || !itemMap.has(parentId)) {
      roots.push(item)
      continue
    }

    const siblings = childrenMap.get(parentId) || []
    siblings.push(item)
    childrenMap.set(parentId, siblings)
  }

  return roots.map(parent => ({
    parent,
    children: childrenMap.get(parent.id) || [],
  }))
})

function getPinnedKey(item: Api.Project.MyProjectInfo) {
  return item?.id ? `${PinnedResourceType.Project}:${item.id}` : null
}

function isPinned(item: Api.Project.MyProjectInfo) {
  const key = getPinnedKey(item)
  if (!key || !props.pinnedMap) {
    return false
  }
  return props.pinnedMap.has(key)
}

function isPinning(item: Api.Project.MyProjectInfo) {
  const key = getPinnedKey(item)
  if (!key || !props.pinningKeys) {
    return false
  }
  return props.pinningKeys.has(key)
}

function handleTogglePin(item: Api.Project.MyProjectInfo, event: MouseEvent) {
  event.preventDefault()
  event.stopPropagation()
  if (!item?.id) {
    return
  }
  emits("togglePin", { resourceType: PinnedResourceType.Project, resourceId: item.id })
}

function getSubprojectCountLabel(count: number) {
  return count === 1
    ? $t("page.project.settingsPage.subprojectCountSingle", { count })
    : $t("page.project.settingsPage.subprojectCountPlural", { count })
}

function visibleChildren(children: Api.Project.MyProjectInfo[]) {
  return props.showPrivate ? children : children.filter(item => item.type !== 1)
}

function hasVisibleChildren(children: Api.Project.MyProjectInfo[]) {
  return visibleChildren(children).length > 0
}
</script>

<style scoped lang="sass">
.pin-action
  opacity: 1
  transition: opacity .2s ease

.pin-action--active
  opacity: 1
</style>

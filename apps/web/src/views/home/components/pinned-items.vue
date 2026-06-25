<template>
  <n-card bordered class="rounded-2.5" content-class="!p-0">
    <template #header>
      <div class="flex items-center justify-between">
        <span class="text-4 font-500">{{ $t("page.home.pinned") }}</span>
        <div class="flex items-center gap-2">
          <span class="text-3 text-gray-500">{{ props.items.length }}/{{ props.maxCount }}</span>
          <pinned-manage-modal
            :pinned-map="pinnedMap"
            :pinning-keys="props.pinningKeys"
            :max-count="props.maxCount"
            @togglePin="payload => emits('togglePin', payload)"
          />
        </div>
      </div>
    </template>
    <n-spin :show="props.loading" class="min-h-20">
      <div v-if="displayItems.length > 0" ref="listRef" class="pinned-list">
        <div v-for="{ item, meta } in displayItems" :key="item.id" class="pinned-row group" :data-id="item.id">
          <n-tooltip placement="top">
            <template #trigger>
              <span class="pinned-drag-handle">
                <n-icon :component="GripIcon" :size="16" />
              </span>
            </template>
            {{ $t("page.home.pinnedReorderHint") }}
          </n-tooltip>
          <div class="pinned-icon">
            <n-avatar
              v-if="meta.icon === 'lab' && meta.logoUrl"
              :src="meta.logoUrl"
              :size="40"
              color="transparent"
              object-fit="cover"
            />
            <lab-icon v-else-if="meta.icon === 'lab'" color="#A1A4AF" />
            <project-icon v-else-if="meta.icon === 'project'" color="#A1A4AF" />
            <research-icon v-else color="#A1A4AF" :size="40" />
          </div>
          <div class="pinned-content">
            <div class="pinned-title-row">
              <n-ellipsis :line-clamp="1" :tooltip="{ placement: 'top' }" class="pinned-title">
                <router-link v-if="meta.route" :to="meta.route" class="hover:router-link">
                  {{ meta.title }}
                </router-link>
                <span v-else>{{ meta.title }}</span>
              </n-ellipsis>
              <span
                v-if="meta.visibilityLabel"
                class="pinned-visibility"
                :class="meta.visibilityClass"
              >
                {{ meta.visibilityLabel }}
              </span>
            </div>
            <n-ellipsis
              v-if="meta.subtitle || (meta.subtitleParts && meta.subtitleParts.length > 0)"
              :line-clamp="1"
              :tooltip="false"
              class="pinned-subtitle"
            >
              <template v-if="meta.subtitleParts && meta.subtitleParts.length > 0">
                <template v-for="(part, index) in meta.subtitleParts" :key="`${part.label}-${index}`">
                  <span v-if="index > 0" class="subtitle-sep">/</span>
                  <router-link v-if="part.route" :to="part.route" class="hover:router-link">
                    {{ part.label }}
                  </router-link>
                  <span v-else>{{ part.label }}</span>
                </template>
              </template>
              <template v-else>
                <router-link
                  v-if="meta.subtitleRoute"
                  :to="meta.subtitleRoute"
                  class="hover:router-link"
                >
                  {{ meta.subtitle }}
                </router-link>
                <span v-else>{{ meta.subtitle }}</span>
              </template>
            </n-ellipsis>
          </div>
          <n-tooltip>
            <template #trigger>
              <n-button
                quaternary
                size="small"
                class="pin-action"
                :class="{ 'pin-action--active': isPinning(item) }"
                :loading="isPinning(item)"
                @click="handleToggle(item, $event)"
              >
                <n-icon :component="PinnedIcon" :size="16" color="#0084E2" />
              </n-button>
            </template>
            {{ $t("icon.unpin") }}
          </n-tooltip>
        </div>
      </div>
      <div v-else-if="!props.loading" class="pinned-empty">
        <div class="text-3 text-gray-500">
          {{ $t("page.home.pinnedEmptyTitle") }}
        </div>
        <div class="text-3 text-gray-400">
          {{ $t("page.home.pinnedEmptyDesc") }}
        </div>
      </div>
    </n-spin>
  </n-card>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import type { RouteLocationRaw } from "vue-router"
import LabIcon from "@/components/icon/lab-icon.vue"
import ProjectIcon from "@/components/icon/project-icon.vue"
import ResearchIcon from "@/components/icon/protocol-icon.vue"
import { ProjectType } from "@/enum"
import { type PinnedItem, PinnedResourceType } from "@/service/api/pinned-items"
import { formatNumber } from "@airalogy/shared"
import { $t } from "@airalogy/shared/locales"
import GripIcon from "~icons/tabler/grip-vertical"
import PinnedIcon from "~icons/tabler/pinned"
import Sortable from "sortablejs"
import PinnedManageModal from "./pinned-manage-modal.vue"

interface Props {
  items: PinnedItem[]
  loading?: boolean
  pinningKeys?: Set<string>
  maxCount?: number
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  maxCount: 10,
})

const emits = defineEmits<{
  (ev: "togglePin", payload: { resourceType: PinnedResourceType, resourceId: string }): void
  (ev: "reorderPinned", pinnedItemIds: number[]): void
}>()

const pinnedMap = computed(() => {
  const map = new Map<string, PinnedItem>()
  props.items.forEach((item) => {
    map.set(`${item.resource_type}:${item.resource_id}`, item)
  })
  return map
})

interface PinnedItemMeta {
  title: string
  subtitle?: string
  subtitleRoute?: RouteLocationRaw | null
  subtitleParts?: Array<{ label: string, route?: RouteLocationRaw | null }>
  route?: RouteLocationRaw | null
  visibilityLabel?: string
  visibilityClass?: string
  icon: "lab" | "project" | "protocol"
  logoUrl?: string | null
}

function resolveProjectVisibility(type?: ProjectType | null) {
  if (type === ProjectType.PRIVATE) {
    return {
      label: $t("page.project.settingsPage.visibility.privateLabel"),
      className: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200",
    }
  }
  if (type === ProjectType.PUBLIC) {
    return {
      label: $t("page.project.settingsPage.visibility.publicLabel"),
      className: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200",
    }
  }
  return {
    label: "",
    className: "",
  }
}

function resolveItemMeta(item: PinnedItem): PinnedItemMeta {
  if (item.resource_type === PinnedResourceType.Lab) {
    const resource = item.resource as Api.Lab.LabInfo
    const projectCount = formatNumber(resource.projects_count || 0)
    const memberCount = formatNumber(resource.users_count || 0)
    return {
      title: resource.name || resource.uid || "Untitled lab",
      subtitle: $t("page.home.pinnedLabMeta", { projectCount, memberCount }),
      route: resource.uid ? { name: "lab-projects", params: { labUid: resource.uid } } : null,
      icon: "lab",
      logoUrl: resource.logo_url || null,
    }
  }

  if (item.resource_type === PinnedResourceType.Project) {
    const resource = item.resource as Api.Project.MyProjectInfo
    const labLabel = resource.lab_name || resource.lab_uid || ""
    const visibility = resolveProjectVisibility(resource.type)
    return {
      title: resource.name || resource.uid || "Untitled project",
      subtitle: labLabel || undefined,
      subtitleRoute: resource.lab_uid ? { name: "lab-projects", params: { labUid: resource.lab_uid } } : null,
      visibilityLabel: visibility.label || undefined,
      visibilityClass: visibility.className || undefined,
      subtitleParts: labLabel
        ? [
            {
              label: labLabel,
              route: resource.lab_uid ? { name: "lab-projects", params: { labUid: resource.lab_uid } } : null,
            },
          ]
        : undefined,
      route:
        resource.lab_uid && resource.uid
          ? { name: "project-protocols", params: { labUid: resource.lab_uid, projectUid: resource.uid } }
          : null,
      icon: "project",
    }
  }

  const resource = item.resource as Partial<ProtocolModels.ProjectProtocolInfo & ProtocolModels.ProtocolResponseInfo>
  const labUid = resource.lab?.uid || resource.lab_uid
  const projectUid = resource.project?.uid || resource.project_uid
  const labLabel = resource.lab?.name || resource.lab_name || resource.lab_uid || ""
  const projectLabel = resource.project?.name || resource.project_name || resource.project_uid || ""
  const subtitle = [labLabel, projectLabel].filter(Boolean).join(" / ")
  const subtitleParts = [
    labLabel
      ? {
          label: labLabel,
          route: labUid ? { name: "lab-projects", params: { labUid } } : null,
        }
      : null,
    projectLabel
      ? {
          label: projectLabel,
          route: labUid && projectUid ? { name: "project-protocols", params: { labUid, projectUid } } : null,
        }
      : null,
  ].filter(Boolean) as Array<{ label: string, route?: RouteLocationRaw | null }>

  return {
    title: resource.name || resource.uid || "Untitled protocol",
    subtitle: subtitle || undefined,
    subtitleParts: subtitleParts.length > 0 ? subtitleParts : undefined,
    route:
      labUid && projectUid && resource.uid
        ? { name: "protocol-info", params: { labUid, projectUid, protocolUid: resource.uid } }
        : null,
    icon: "protocol",
  }
}

const displayItems = computed(() => props.items.map(item => ({ item, meta: resolveItemMeta(item) })))

const listRef = ref<HTMLElement | null>(null)
const sortableRef = ref<Sortable | null>(null)

function destroySortable() {
  if (sortableRef.value) {
    sortableRef.value.destroy()
    sortableRef.value = null
  }
}

function collectPinnedOrder() {
  if (!listRef.value) {
    return []
  }
  return Array.from(listRef.value.children)
    .map(el => Number((el as HTMLElement).dataset.id))
    .filter(id => Number.isFinite(id))
}

function initSortable() {
  if (!listRef.value) {
    return
  }
  destroySortable()
  sortableRef.value = new Sortable(listRef.value, {
    animation: 150,
    handle: ".pinned-drag-handle",
    ghostClass: "pinned-ghost",
    chosenClass: "pinned-chosen",
    onEnd: () => {
      const order = collectPinnedOrder()
      if (order.length > 0) {
        emits("reorderPinned", order)
      }
    },
  })
  sortableRef.value.option("disabled", props.loading || displayItems.value.length < 2)
}

watch([listRef, () => displayItems.value.length, () => props.loading], () => {
  if (!listRef.value || displayItems.value.length < 2) {
    destroySortable()
    return
  }
  if (!sortableRef.value) {
    initSortable()
  }
  else {
    sortableRef.value.option("disabled", props.loading)
  }
})

onBeforeUnmount(() => {
  destroySortable()
})

function getKey(item: PinnedItem) {
  return `${item.resource_type}:${item.resource_id}`
}

function isPinning(item: PinnedItem) {
  return props.pinningKeys?.has(getKey(item)) || false
}

function handleToggle(item: PinnedItem, event: MouseEvent) {
  event.preventDefault()
  event.stopPropagation()
  emits("togglePin", { resourceType: item.resource_type, resourceId: item.resource_id })
}
</script>

<style scoped lang="sass">
.pinned-list
  display: flex
  flex-direction: column
  gap: 6px
  padding: 8px 16px 12px

.pinned-row
  display: flex
  align-items: center
  gap: 12px
  padding: 8px 10px
  border-radius: 12px
  transition: background-color .2s ease

.pinned-drag-handle
  display: inline-flex
  align-items: center
  justify-content: center
  width: 20px
  height: 20px
  color: #A1A4AF
  cursor: grab
  flex-shrink: 0

.pinned-drag-handle:active
  cursor: grabbing

.pinned-row:hover
  background: #F5F6F8

.pinned-icon
  width: 40px
  height: 40px
  display: flex
  align-items: center
  justify-content: center

.pinned-content
  min-width: 0
  flex: 1
  display: flex
  flex-direction: column
  gap: 4px

.pinned-title-row
  display: flex
  align-items: center
  gap: 8px
  min-width: 0

.pinned-title
  min-width: 0
  flex: 1

.pinned-visibility
  padding: 2px 8px
  border-radius: 999px
  font-size: 11px
  line-height: 1
  white-space: nowrap

.pinned-subtitle
  display: block
  font-size: 12px
  color: #6B7280

.subtitle-sep
  margin: 0 4px
  color: #9CA3AF

.pinned-empty
  padding: 20px 16px 24px
  text-align: center
  display: flex
  flex-direction: column
  gap: 6px

.pin-action
  opacity: 0
  transition: opacity .2s ease

.pinned-row:hover .pin-action
  opacity: 1

.pin-action--active
  opacity: 1

.pinned-ghost
  opacity: 0.6
  background: #EEF1F6

.pinned-chosen
  background: #F5F6F8
</style>

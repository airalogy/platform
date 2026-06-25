<template>
  <n-list clickable hoverable>
    <template v-for="item in props.list" :key="item.id">
      <n-list-item>
        <template #prefix>
          <n-icon :size="40">
            <icon-local-protocol />
          </n-icon>
        </template>
        <div class="min-w-0 flex-1">
          <project-protocol-item :item="item" :is-compact="false" />
          <div v-if="hasFolders && getFolderNames(item).length" class="mt-1 flex flex-wrap gap-1">
            <n-tag
              v-for="name in getFolderNames(item).slice(0, 3)"
              :key="name"
              size="small"
              type="info"
            >
              {{ name }}
            </n-tag>
            <n-tag
              v-if="getFolderNames(item).length > 3"
              size="small"
              type="info"
            >
              +{{ getFolderNames(item).length - 3 }}
            </n-tag>
          </div>
        </div>
        <template #suffix>
          <div v-if="showActionArea" class="flex items-center gap-2">
            <template v-if="canViewOthersRecords || canViewOwnRecords">
              <n-button
                ghost
                :bordered="false"
                :theme-overrides="{ textColor: '#333333' }"
                @click="() => handleNavigateLogs(item)"
              >
                {{ item.records_count }}
                <template #icon>
                  <schema-icon />
                </template>
              </n-button>
              <div class="metric-stat" :title="$t('common.starsCount')">
                <n-icon :size="14">
                  <icon-tabler-star />
                </n-icon>
                <span>{{ formatNumber(item.stars_count || 0) }}</span>
              </div>
              <div class="metric-stat" :title="$t('common.reusesCount')">
                <n-icon :size="14">
                  <icon-local-reuse />
                </n-icon>
                <span>{{ formatNumber(item.forks_count || 0) }}</span>
              </div>
            </template>
            <n-popover v-if="hasFolders" trigger="click" placement="top" class="ml-1">
              <template #trigger>
                <n-button
                  quaternary
                  size="small"
                  :disabled="!canEditFolders(item)"
                  :loading="isFolderUpdating(item)"
                >
                  <n-icon :component="FolderIcon" :size="16" />
                </n-button>
              </template>
              <div class="w-64">
                <div class="mb-2 text-xs text-gray-500">
                  {{ canEditFolders(item) ? $t("page.project.protocolFolders.assignHint") : $t("page.project.protocolFolders.noPermissionHint") }}
                </div>
                <n-select
                  :value="getFolderSelection(item)"
                  :options="folderOptions"
                  multiple
                  clearable
                  :disabled="!canEditFolders(item)"
                  :loading="isFolderUpdating(item)"
                  @update:value="(value) => handleFolderChange(item, value)"
                />
              </div>
            </n-popover>
            <n-tooltip v-if="showPin" placement="top" class="ml-auto">
              <template #trigger>
                <n-button
                  quaternary
                  size="small"
                  class="pin-action"
                  :class="{ 'pin-action--active': isPinning(item) }"
                  :loading="isPinning(item)"
                  @click.stop="handleTogglePin(item, $event)"
                >
                  <n-icon
                    :component="PinnedIcon"
                    :size="16"
                    :color="isPinned(item) ? '#0084E2' : '#A1A4AF'"
                  />
                </n-button>
              </template>
              {{ isPinned(item) ? $t("icon.unpin") : $t("icon.pin") }}
            </n-tooltip>
            <delete-button
              v-if="showDeleteAction"
              :disabled="!canDeleteProtocol(item)"
              @click="() => handleDeleteResearch(item)"
            />
            <!-- <edit-protocol-modal :item="item" @modal:edit-research="handleEditResearch" />
            <delete-button @click="handleDeleteResearch(item)" /> -->
          </div>
        </template>
      </n-list-item>
    </template>
  </n-list>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"

import type { SelectOption } from "naive-ui"
import { useProjectPermissions } from "@/composables"
import { LAB_OWNER_AND_MANAGER } from "@/composables/useLabPermissions"

import { useRouterPush } from "@/composables/useRouterPush"
import { type PinnedItem, PinnedResourceType } from "@/service/api/pinned-items"
import { deleteProtocol } from "@/service/api/project-protocols"
import { putProtocolFolders } from "@/service/api/protocol-folders"
import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"
import { useOrProvideProjectInfoStore } from "@/views/project-protocols/hooks/useProjectInfoStore"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { formatNumber } from "@airalogy/shared/utils"
import FolderIcon from "~icons/tabler/folder"
import PinnedIcon from "~icons/tabler/pinned"
import { useDialog } from "naive-ui"
import ProjectProtocolItem from "./project-protocol-item.vue"

defineOptions({ name: "LabProjectList" })

const props = withDefaults(defineProps<IProps>(), {
  list: () => [],
  showActions: true,
})

const emits = defineEmits<{
  (ev: "togglePin", payload: { resourceType: PinnedResourceType, resourceId: string }): void
  (ev: "foldersUpdated", payload: { protocolId: string, folderIds: number[] }): void
}>()

interface IProps {
  list: ProtocolModels.ProjectProtocolInfo[]
  pinnedMap?: Map<string, PinnedItem>
  pinningKeys?: Set<string>
  folders?: Api.ProtocolFolder.Folder[]
  showActions?: boolean
}

const { routerPushByKey } = useRouterPush()

const message = useClosableMessage()

const dialog = useDialog()

const { userInfo } = useAuthStore()
const { reloadPage } = useAppStore()
const { projectInfo } = useOrProvideProjectInfoStore(null)
const {
  canViewOthersRecords,
  canViewOwnRecords,
  canShowSettings,
  canManageOwnProtocols,
  canManageOthersProtocols,
} = useProjectPermissions(projectInfo)

const folderSelections = ref(new Map<string, number[]>())
const folderUpdating = ref(new Set<string>())

const isLabAdmin = computed(() => {
  const role = projectInfo.value?.user_lab_role
  return Boolean(role) && LAB_OWNER_AND_MANAGER.includes(role)
})

const hasFolders = computed(() => (props.folders?.length || 0) > 0)
const folderOptions = computed<SelectOption[]>(() =>
  (props.folders || []).map(folder => ({
    label: folder.name,
    value: folder.id,
  })),
)
const folderNameMap = computed(() => new Map((props.folders || []).map(folder => [folder.id, folder.name])))

watch(
  () => props.list,
  (list) => {
    const next = new Map<string, number[]>()
    list.forEach((item) => {
      const ids = Array.isArray(item.folder_ids) ? item.folder_ids : []
      next.set(item.id, [...ids])
    })
    folderSelections.value = next
  },
  { immediate: true },
)

const showPin = computed(() => Boolean(props.pinnedMap))
const showDeleteAction = computed(() => Boolean(projectInfo.value))
const showActions = computed(() => props.showActions !== false)
const showActionArea = computed(() =>
  showActions.value && (
    showPin.value
    || canViewOthersRecords.value
    || canViewOwnRecords.value
    || hasFolders.value
    || showDeleteAction.value
  ),
)

function getPinnedKey(item: ProtocolModels.ProjectProtocolInfo) {
  return item?.id ? `${PinnedResourceType.Protocol}:${item.id}` : null
}

function isPinned(item: ProtocolModels.ProjectProtocolInfo) {
  const key = getPinnedKey(item)
  if (!key || !props.pinnedMap) {
    return false
  }
  return props.pinnedMap.has(key)
}

function isPinning(item: ProtocolModels.ProjectProtocolInfo) {
  const key = getPinnedKey(item)
  if (!key || !props.pinningKeys) {
    return false
  }
  return props.pinningKeys.has(key)
}

function getFolderSelection(item: ProtocolModels.ProjectProtocolInfo) {
  return folderSelections.value.get(item.id) || []
}

function getFolderNames(item: ProtocolModels.ProjectProtocolInfo) {
  const selection = getFolderSelection(item)
  return selection.map(id => folderNameMap.value.get(id)).filter(Boolean) as string[]
}

function isFolderUpdating(item: ProtocolModels.ProjectProtocolInfo) {
  return folderUpdating.value.has(item.id)
}

function canEditFolders(item: ProtocolModels.ProjectProtocolInfo) {
  if (canShowSettings.value) {
    return true
  }
  return item.user_id === userInfo.id
}

async function handleFolderChange(item: ProtocolModels.ProjectProtocolInfo, value: Array<string | number> | null) {
  if (!item?.id || !item.project?.id) {
    return
  }

  const next = (value || []).map(v => Number(v)).filter(v => !Number.isNaN(v))
  const prev = getFolderSelection(item)

  folderSelections.value.set(item.id, [...next])
  folderUpdating.value.add(item.id)
  try {
    const { error } = await putProtocolFolders(item.project.id, item.id, next)
    if (error) {
      folderSelections.value.set(item.id, [...prev])
      return
    }
    item.folder_ids = [...next]
    message.success($t("page.project.protocolFolders.updateSuccess"))
    emits("foldersUpdated", { protocolId: item.id, folderIds: next })
  }
  catch (e) {
    folderSelections.value.set(item.id, [...prev])
  }
  finally {
    folderUpdating.value.delete(item.id)
  }
}

function handleTogglePin(item: ProtocolModels.ProjectProtocolInfo, event: MouseEvent) {
  event.preventDefault()
  event.stopPropagation()
  if (!item?.id) {
    return
  }
  emits("togglePin", { resourceType: PinnedResourceType.Protocol, resourceId: item.id })
}

function canDeleteProtocol(item: ProtocolModels.ProjectProtocolInfo) {
  if (!userInfo?.id || !projectInfo.value) {
    return false
  }
  if (isLabAdmin.value) {
    return true
  }
  if (item.user_id === userInfo.id) {
    return canManageOwnProtocols.value
  }
  return canManageOthersProtocols.value
}

async function handleNavigateLogs(item: ProtocolModels.ProjectProtocolInfo) {
  const { uid, project, lab } = item

  await routerPushByKey("protocol-records", {
    params: { protocolUid: uid, projectUid: project.uid, labUid: lab.uid },
  })
}

function handleDeleteResearch(item: ProtocolModels.ProjectProtocolInfo) {
  if (!canDeleteProtocol(item)) {
    return
  }
  const isAdminDelete = Boolean(
    userInfo?.id
    && item.user_id !== userInfo.id
    && (canManageOthersProtocols.value || isLabAdmin.value),
  )
  const content = isAdminDelete
    ? `${$t("page.protocol.settings.deleteDescription")} ${$t("page.protocol.settings.adminDeleteNotice")}`
    : $t("page.protocol.settings.deleteDescription")
  const { id, name } = item
  const d = dialog.error({
    title: $t("page.protocol.settings.deleteTitle"),
    content,
    positiveText: $t("common.delete"),
    negativeText: $t("common.cancel"),
    onPositiveClick: async () => {
      d.loading = true

      try {
        const success = await deleteProtocol(id)
        if (success) {
          await reloadPage(10)
          message.success(`Successfully deleted protocol ${name}`)
          return true
        }

        return false
      }
      catch (e) {
        // NOPE
        return false
      }
      finally {
        d.loading = false
      }
    },
  })
}

async function handleEditResearch() {
  await reloadPage(10)
}
</script>

<style scoped lang="sass">
.metric-stat
  min-width: 40px
  display: inline-flex
  align-items: center
  gap: 6px
  color: #333333
  font-size: 14px

.metric-stat :deep(.n-icon)
  color: #A1A4AF

.pin-action
  opacity: 1
  transition: opacity .2s ease

.pin-action--active
  opacity: 1
</style>

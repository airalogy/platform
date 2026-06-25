<template>
  <tooltip-button v-auth :tooltip="props.tooltip" v-bind="triggerButtonProps" @click.stop="handleTriggerClick">
    <template v-if="props.showIcon" #icon>
      <n-icon v-bind="props.iconProps">
        <icon-tabler-star-filled />
      </n-icon>
    </template>
    <slot name="trigger">
      {{ props.trigger }}
    </slot>
  </tooltip-button>
  <n-modal
    :show="isShown"
    preset="card"
    :title="$t('common.myStarred')"
    :bordered="false"
    size="huge"
    class="w-160"
    :mask-closable="false"
    :loading="loading"
    content-class="!px-7.5 !py-0"
    footer-class="flex items-center"
    @update:show="handleSetShow"
  >
    <div class="mb-5">
      <template v-if="starredFolders.length > 0">
        <file-tree
          v-model:selected-keys="selectedFolders"
          v-model:checked-keys="selectedFolders"
          :elements="treeElements"
          :tree-props="{
            themeOverrides: { nodeHeight: '48px', fontSize: '1rem', nodeTextColorDisabled: '#666' },
            checkable: true,
            multiple: true,
            checkOnClick: true,
            expandOnClick: false,
            checkableFilter: handleCheckable,
            onLoad: handleLoadFolderContent,
          }"
          class="max-h-60vh"
          :custom-actions="handleItemAction"
          @update:item="handleUpdateFolderName"
          @select="handleTreeItemSelect"
          @context-menu-select="handleContextMenuSelect"
          @keydown.esc.stop
        />
      </template>

      <div v-else class="py-5 text-center text-gray-500">
        {{ $t("common.noFoldersYet") }}
      </div>
    </div>
    <template #footer>
      <n-button text type="primary" @click="handleAddNewFolder">
        <template #icon>
          <n-icon :component="AddCircleOutline" :size="20" />
        </template>
        {{ $t("common.newFolder") }}
      </n-button>

      <n-button size="medium" class="ml-auto mr-4" :disabled="loading" @click="handleCancel">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button
        size="medium"
        type="primary"
        :disabled="loading || !hasSelectedFolders"
        :loading="loading"
        @click="handleConfirm"
      >
        {{ $t("common.confirm") }}
      </n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { NIcon, TreeOption } from "naive-ui"
import type { ButtonProps } from "naive-ui/es/button"
import type { TmNode } from "naive-ui/es/tree/src/interface"
import type { Action } from "./file-tree/Actions.vue"
import FileTree, { type TreeViewElement } from "@/components/common/file-tree/index.vue"
import { useLoading, useShowModal } from "@/composables"
import { getQuestionDetail } from "@/service/api/discussion"
import { getProtocolInfo } from "@/service/api/project-protocols"
import {
  createStar,
  createStarFolder,
  deleteStar,
  deleteStarFolder,
  getStarFolders,
  getStars,
  type StarFolder,
  StarResourceType,
  type StarResponse,
  updateStar,
  updateStarFolder,
} from "@/service/api/star"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import AddCircleOutline from "~icons/ion/add-circle-outline"
import OpenIcon from "~icons/ion/open-outline"
import ProtocolIcon from "~icons/local/protocol-outline"
import AnswerIcon from "~icons/tabler/message"
import QuestionIcon from "~icons/tabler/message-2-question"
import TrashIcon from "~icons/tabler/trash"
import { h, onUnmounted } from "vue"
import { useRouterPush } from "../../composables/useRouterPush"

// Extended StarFolder interface to include status property needed for UI
export interface StarredFolder extends Omit<StarFolder, "created_at" | "updated_at"> {
  status?: "pending" | "success"
  createdAt?: string
  updatedAt?: string
  isTemp?: boolean // Flag to track temporary folders
  children?: StarItem[] // Add children for starred items
  isLoading?: boolean // Flag to track loading state
}

// Interface for star items
interface StarItem {
  id: number
  resourceType: StarResourceType
  resourceId: string
  resourceName?: string // This would need to be populated based on the resource type and ID
  folderIds: number[]
  createdAt: string
}

interface IProps {
  showIcon?: boolean
  iconProps?: Partial<InstanceType<typeof NIcon>["$props"]>
  buttonProps?: ButtonProps & { class?: string }
  trigger?: string
  projectId?: string
  protocolId?: string
  answerId?: string
  questionId?: string
  tooltip?: string
  type: "protocol" | "answer" | "question"
  starred?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  showIcon: true,
  trigger: "Add to bookmarker",
  buttonProps: () => ({}),
  starred: false,
})

const emits = defineEmits<{
  (e: "modal:add-to-bookmarker", folders: StarredFolder[]): void
  (e: "modal:close"): void
  (e: "modal:open"): void
  (e: "modal:new-folder", folderId: string): void
}>()

const DEFAULT_FOLDER_CANONICAL_NAME = "default"

const message = useClosableMessage()
const { isShown, showModal, hideModal, setModalStatus } = useShowModal()
const { loading, startLoading, endLoading } = useLoading()
const isManagingExistingStar = ref(false)
const currentStar = ref<StarResponse | null>(null)
const starStateOverride = ref<boolean | null>(null)
const undoUnstarContext = ref<UndoUnstarContext | null>(null)

// Normally you would fetch these from an API
const starredFolders = ref<StarredFolder[]>([])

const selectedFolders = ref<string[]>([])

// Add a map to track loaded folders
const loadedFolderContents = ref<Record<string, boolean>>({})
const folderLoadingStates = ref<Record<string, boolean>>({})

const treeElements = computed<TreeViewElement[]>(() => {
  return starredFolders.value.map(folder => ({
    id: folder.id.toString(),
    filename: getFolderDisplayName(folder),
    kind: "directory",
    status: folder.status || (folder.name === "" ? "pending" : "success"),
    isEditable: true,
    isSelectable: folder.name !== "",
    path: folder.id.toString(),
    children: folder.children?.map(child => ({
      id: child.id.toString(),
      filename: child.resourceName || "",
      kind: "file",
      status: "success",
      isEditable: false,
      isSelectable: false,
      path: `${folder.id}/${child.id}`,
      value: child.resourceId,
      icon: child.resourceType === StarResourceType.Protocol ? ProtocolIcon : child.resourceType === StarResourceType.Answer ? AnswerIcon : QuestionIcon,
    })),
    isLoading: folderLoadingStates.value[folder.id] || false,
    isLeaf: true,
  }))
})

const hasSelectedFolders = computed(() => {
  return selectedFolders.value.length > 0
})

const defaultFolderId = computed<number | null>(() => findNamedDefaultFolder(starredFolders.value)?.id ?? null)

const isStarredStyle = computed(() => {
  if (typeof starStateOverride.value === "boolean") {
    return starStateOverride.value
  }
  return props.starred
})

const triggerButtonProps = computed<ButtonProps & { class?: string }>(() => {
  const classNames = [
    "star-trigger-button",
    isStarredStyle.value ? "is-starred" : "",
    props.buttonProps?.class || "",
  ]
    .filter(Boolean)
    .join(" ")

  return {
    ...(props.buttonProps || {}),
    class: classNames,
  }
})

function handleSetShow(val: boolean) {
  setModalStatus(val)
}

function handleCancel() {
  hideModal()
}

interface CurrentStarResource {
  resourceType: StarResourceType
  resourceId: string
}

interface UndoUnstarContext {
  resource: CurrentStarResource
  folderIds: number[]
  timer: ReturnType<typeof setTimeout>
}

function resolveCurrentResource(): CurrentStarResource | null {
  if (props.type === "protocol" && props.protocolId) {
    return { resourceType: StarResourceType.Protocol, resourceId: props.protocolId }
  }

  if (props.type === "answer" && props.answerId) {
    return { resourceType: StarResourceType.Answer, resourceId: props.answerId }
  }

  if (props.type === "question" && props.questionId) {
    return { resourceType: StarResourceType.Question, resourceId: props.questionId }
  }

  return null
}

function isSameResource(a: CurrentStarResource, b: CurrentStarResource) {
  return a.resourceType === b.resourceType && String(a.resourceId) === String(b.resourceId)
}

function isAlreadyStarredError(error: unknown) {
  return (error as Error)?.message?.toLowerCase()?.includes("already starred")
}

function toStarredFolder(folder: StarFolder): StarredFolder {
  return {
    ...folder,
    status: "success",
    createdAt: folder.created_at,
    updatedAt: folder.updated_at,
  }
}

function normalizeFolderName(name?: string | null) {
  return String(name || "").trim().toLocaleLowerCase()
}

function isDefaultFolderName(name?: string | null) {
  const normalized = normalizeFolderName(name)
  return normalized === DEFAULT_FOLDER_CANONICAL_NAME
    || normalized === "default folder"
    || normalized === "默认收藏夹"
    || normalized === normalizeFolderName($t("common.defaultFolder"))
}

function isDefaultFolder(folder: StarredFolder) {
  if (typeof folder.is_default === "boolean") {
    return folder.is_default
  }
  return isDefaultFolderName(folder.name)
}

function findNamedDefaultFolder(folders: StarredFolder[]): StarredFolder | null {
  return folders.find(folder => folder.id > 0 && isDefaultFolder(folder)) || null
}

function getFolderDisplayName(folder: StarredFolder) {
  if (isDefaultFolder(folder)) {
    return $t("common.defaultFolder")
  }
  return folder.name
}

function pickDefaultFolder(folders: StarredFolder[]): StarredFolder | null {
  const namedDefaultFolder = findNamedDefaultFolder(folders)
  if (namedDefaultFolder) {
    return namedDefaultFolder
  }

  const availableFolders = folders.filter(folder => folder.id > 0 && folder.name)
  if (!availableFolders.length) {
    return null
  }

  return availableFolders.reduce((oldest, folder) => (folder.id < oldest.id ? folder : oldest), availableFolders[0]!)
}

async function findCurrentStar(resourceType: StarResourceType, resourceId: string): Promise<StarResponse | null> {
  const pageSize = 100
  let page = 1

  while (true) {
    const result = await getStars({
      resource_type: resourceType,
      page,
      page_size: pageSize,
    })

    if (!result) {
      return null
    }

    const target = result.stars.find(star => String(star.resource_id) === String(resourceId))
    if (target) {
      return target
    }

    const totalCount = result.total_count || 0
    if (page * pageSize >= totalCount) {
      return null
    }
    page += 1
  }
}

function clearUndoUnstarContext() {
  if (undoUnstarContext.value) {
    clearTimeout(undoUnstarContext.value.timer)
  }
  undoUnstarContext.value = null
}

async function undoUnstar(resource: CurrentStarResource, folderIds: number[]) {
  startLoading()
  try {
    await createStar({
      type: resource.resourceType,
      id: resource.resourceId,
      folderIdList: folderIds,
    })
  }
  catch (error) {
    if (!isAlreadyStarredError(error)) {
      message.error((error as Error).message)
      return
    }
  }
  finally {
    endLoading()
  }

  currentStar.value = await findCurrentStar(resource.resourceType, resource.resourceId)
  starStateOverride.value = true
  if (!starredFolders.value.length) {
    await loadFolders(false)
  }
  const selected = starredFolders.value.filter(folder => folderIds.includes(folder.id))
  if (selected.length > 0) {
    emits("modal:add-to-bookmarker", selected)
  }
  else {
    emits("modal:add-to-bookmarker", [{ id: -1, user_id: "", name: "", status: "success" }])
  }
}

function showUndoUnstarMessage(resource: CurrentStarResource, folderIds: number[]) {
  clearUndoUnstarContext()

  const timer = setTimeout(() => {
    undoUnstarContext.value = null
  }, 5000)
  undoUnstarContext.value = { resource, folderIds, timer }

  message.info(
    () => h("span", [
      `${$t("common.unstar")} `,
      h(
        "button",
        {
          style: {
            marginLeft: "8px",
            cursor: "pointer",
            border: "none",
            background: "transparent",
            padding: "0",
            color: "#1A79FF",
          },
          onClick: async (event: MouseEvent) => {
            event.stopPropagation()
            const context = undoUnstarContext.value
            if (!context || !isSameResource(context.resource, resource)) {
              return
            }
            clearUndoUnstarContext()
            await undoUnstar(context.resource, context.folderIds)
          },
        },
        $t("common.undo"),
      ),
    ]),
    { duration: 5000, closable: true },
  )
}

async function ensureDefaultFolder(): Promise<StarredFolder> {
  const folders = await loadFolders(false)
  const existingDefaultFolder = findNamedDefaultFolder(folders)
  if (existingDefaultFolder) {
    return existingDefaultFolder
  }

  const createdFolder = await createStarFolder(DEFAULT_FOLDER_CANONICAL_NAME)
  if (createdFolder) {
    const defaultFolder = toStarredFolder(createdFolder)
    starredFolders.value = [...starredFolders.value, defaultFolder]
    return defaultFolder
  }

  // Retry once by refetching folders to tolerate concurrent folder creation failures.
  const refreshedFolders = await loadFolders(false)
  const fallbackDefaultFolder = findNamedDefaultFolder(refreshedFolders) || pickDefaultFolder(refreshedFolders)
  if (fallbackDefaultFolder) {
    return fallbackDefaultFolder
  }

  throw new Error("Failed to create default folder")
}

async function openFolderSwitcher(resource: CurrentStarResource, withLoading = true) {
  if (withLoading) {
    startLoading()
  }
  try {
    const [foundStar] = await Promise.all([
      findCurrentStar(resource.resourceType, resource.resourceId),
      loadFolders(false),
    ])

    if (props.starred && !foundStar) {
      message.error("Failed to load current star")
      return
    }

    currentStar.value = foundStar
    starStateOverride.value = Boolean(foundStar)
    selectedFolders.value = foundStar?.folder_ids?.map(id => id.toString()) || []
    isManagingExistingStar.value = Boolean(foundStar)
    showModal()
  }
  catch (error) {
    message.error((error as Error).message)
  }
  finally {
    if (withLoading) {
      endLoading()
    }
  }
}

async function quickStarToDefaultFolder(resource: CurrentStarResource) {
  startLoading()
  try {
    const defaultFolder = await ensureDefaultFolder()

    const createdStar = await createStar({
      type: resource.resourceType,
      id: resource.resourceId,
      folderIdList: [defaultFolder.id],
    })

    currentStar.value = createdStar || await findCurrentStar(resource.resourceType, resource.resourceId)
    starStateOverride.value = true
    emits("modal:add-to-bookmarker", [defaultFolder])

    selectedFolders.value = currentStar.value?.folder_ids?.map(id => id.toString()) || [defaultFolder.id.toString()]
    // We have just created a star, treat subsequent confirm as update flow.
    isManagingExistingStar.value = true

    showModal()
  }
  catch (error) {
    if (isAlreadyStarredError(error)) {
      await openFolderSwitcher(resource, false)
      return
    }
    message.error((error as Error).message)
  }
  finally {
    endLoading()
  }
}

async function unstar(resource: CurrentStarResource) {
  startLoading()
  try {
    let targetStar = currentStar.value
    if (!targetStar) {
      targetStar = await findCurrentStar(resource.resourceType, resource.resourceId)
    }

    if (!targetStar) {
      message.error("Failed to load current star")
      return
    }

    await deleteStar(targetStar.id)

    const folderIds = targetStar.folder_ids || []
    currentStar.value = null
    starStateOverride.value = false
    isManagingExistingStar.value = false
    selectedFolders.value = []
    emits("modal:add-to-bookmarker", [])
    showUndoUnstarMessage(resource, folderIds)
  }
  catch (error) {
    message.error((error as Error).message)
  }
  finally {
    endLoading()
  }
}

async function handleTriggerClick() {
  const resource = resolveCurrentResource()
  if (!resource) {
    message.error("Resource id is required")
    return
  }

  if (undoUnstarContext.value && isSameResource(undoUnstarContext.value.resource, resource)) {
    const context = undoUnstarContext.value
    clearUndoUnstarContext()
    await undoUnstar(context.resource, context.folderIds)
    await openFolderSwitcher(resource, false)
    return
  }

  if (props.starred || currentStar.value) {
    await unstar(resource)
    return
  }

  await quickStarToDefaultFolder(resource)
}

function handleFolderSelect(folder: TreeViewElement) {
  // Only toggle selection for folders with valid names
  if (folder.kind === "directory" && folder.filename) {
    selectedFolders.value = selectedFolders.value.filter(f => f !== folder.id)
  }
}

function handleAddNewFolder() {
  try {
    // Generate a temporary ID for the new folder
    const tempId = Date.now() * -1 // Use negative numbers for temp IDs

    // Add new folder with empty name and pending status
    starredFolders.value.push({
      id: tempId,
      user_id: "",
      name: "",
      status: "pending",
      isTemp: true,
    })

    // Emit event for the new folder
    emits("modal:new-folder", tempId.toString())
  }
  catch (e) {
    message.error((e as Error).message)
  }
}

async function handleUpdateFolderName(id: string, updatedProperties: Record<string, any>) {
  const folderId = Number(id)

  // Find the folder
  const folder = starredFolders.value.find(f => f.id === folderId)
  if (!folder)
    return
  const { status, filename } = updatedProperties

  if (folderId === defaultFolderId.value) {
    const isTryingEnterRename = status === "pending" && filename === undefined
    const isTryingRename = typeof filename === "string" && filename !== folder.name
    if (isTryingEnterRename || isTryingRename) {
      message.warning($t("common.defaultFolderCannotRename"))
      folder.status = "success"
      return
    }
  }

  if (folderId === defaultFolderId.value && filename === "") {
    message.warning($t("common.defaultFolderCannotDelete"))
    return
  }

  if (status === "success") {
    folder.status = "success"
  }

  // Case 1: Change status to pending (entering edit mode)
  if (status === "pending" && filename === undefined) {
    folder.status = "pending"
    return
  }

  // Case 2: Filename is provided (after editing)
  if (filename !== undefined) {
    // If empty name after editing, remove the folder
    if (filename === "") {
      starredFolders.value = starredFolders.value.filter(f => f.id !== folderId)
      selectedFolders.value = selectedFolders.value.filter(f => f !== folderId.toString())
      return
    }

    try {
      // If it's a temporary folder (negative ID), create it on the server
      if (folder.isTemp || Number(folderId) < 0) {
        const newFolder = await createStarFolder(filename)
        if (newFolder) {
          // Replace the temporary folder with the one from the server
          starredFolders.value = starredFolders.value.filter(f => f.id !== folderId)

          starredFolders.value.push({
            ...newFolder,
            status: "success" as const,
            createdAt: newFolder.created_at,
            updatedAt: newFolder.updated_at,
          })

          // Update selection
          selectedFolders.value = selectedFolders.value.filter(f => f !== folderId.toString())
          selectedFolders.value.push(newFolder.id.toString())
        }
      }
      else {
        // Update existing folder
        await updateStarFolder(folderId, filename)
        // Update the folder name locally
        folder.name = filename
        folder.status = "success"
        // Auto-select folders after they are created with a valid name
        selectedFolders.value = selectedFolders.value.filter(f => f !== folderId.toString())
        selectedFolders.value.push(folderId.toString())
      }
    }
    catch (e) {
      message.error((e as Error).message)
    }
  }

  // Case 3: Status is changed to success but no name (editing canceled)
  if (status === "success" && filename === undefined) {
    // If this was a new folder with no name, remove it
    if (!folder.name) {
      starredFolders.value = starredFolders.value.filter(f => f.id !== folderId)
      selectedFolders.value = selectedFolders.value.filter(f => f !== folderId.toString())
    }
    // Otherwise just keep the existing name
  }
}

async function handleContextMenuSelect(action: string, item: TreeViewElement) {
  const { kind, id } = item
  if (action === "delete") {
    try {
      if (kind === "directory") {
        if (Number(id) === defaultFolderId.value) {
          message.warning($t("common.defaultFolderCannotDelete"))
          return
        }

        // Find the folder
        const folder = starredFolders.value.find(f => f.id === Number(id))

        // Only delete from server if it's not a temporary folder
        if (folder && !folder.isTemp && Number(id) > 0) {
          await deleteStarFolder(Number(id))
        }

        // Remove from local state
        starredFolders.value = starredFolders.value.filter(f => f.id.toString() !== id)
        selectedFolders.value = selectedFolders.value.filter(f => f !== id)
      }
      else if (kind === "file") {
        const res = await deleteStar(Number(id))
        if (res) {
          starredFolders.value.forEach(({ children }) => {
            if (!children || children.length === 0) {
              return
            }

            const index = children.findIndex(c => c.id === Number(id))
            if (index !== -1) {
              children.splice(index, 1)
            }
          })
        }
      }
    }
    catch (e) {
      message.error((e as Error).message)
    }
  }
}

function handleTreeItemSelect(item: TreeViewElement) {
  // Don't handle selection for items in edit mode
  if (item.status === "pending")
    return

  if (item.kind === "directory" && item.filename) {
    handleFolderSelect(item)
  }
}

async function handleConfirm() {
  if (!hasSelectedFolders.value) {
    return
  }

  startLoading()

  try {
    const selectedFolderIds = selectedFolders.value.map(id => Number(id)).filter(id => !Number.isNaN(id) && id > 0)
    const selected = starredFolders.value.filter(folder => selectedFolderIds.includes(folder.id))

    if (isManagingExistingStar.value) {
      let targetStar = currentStar.value
      if (!targetStar) {
        const resource = resolveCurrentResource()
        if (resource) {
          targetStar = await findCurrentStar(resource.resourceType, resource.resourceId)
        }
      }

      if (targetStar) {
        await updateStar(targetStar.id, selectedFolderIds)
        currentStar.value = {
          ...targetStar,
          folder_ids: selectedFolderIds,
        }
        starStateOverride.value = true
        message.success("Star folders updated")
        emits("modal:add-to-bookmarker", selected)
        hideModal()
        return
      }
    }

    const resource = resolveCurrentResource()
    if (!resource) {
      message.error("Resource id is required")
      return
    }

    await createStar({
      type: resource.resourceType,
      id: resource.resourceId,
      folderIdList: selectedFolderIds,
    })

    currentStar.value = await findCurrentStar(resource.resourceType, resource.resourceId)
    starStateOverride.value = true
    message.success(`Successfully added to ${selected.length} folder(s)`)
    emits("modal:add-to-bookmarker", selected)
    hideModal()
  }
  catch (e) {
    if (isAlreadyStarredError(e)) {
      const resource = resolveCurrentResource()
      if (resource) {
        await openFolderSwitcher(resource, false)
        return
      }
    }
    message.error((e as Error).message)
  }
  finally {
    endLoading()
  }
}

// Load stars folders function
async function loadFolders(withLoading = true): Promise<StarredFolder[]> {
  try {
    if (withLoading) {
      startLoading()
    }
    const result = await getStarFolders()
    if (result && Array.isArray(result.folders)) {
      // Convert server response to StarredFolder format
      starredFolders.value = result.folders.map(folder => toStarredFolder(folder))

      // Reset loaded folders tracking
      loadedFolderContents.value = {}
      folderLoadingStates.value = {}
    }
    else {
      starredFolders.value = []
    }
    return starredFolders.value
  }
  catch (e) {
    message.error((e as Error).message)
    starredFolders.value = []
    return []
  }
  finally {
    if (withLoading) {
      endLoading()
    }
  }
}

async function handleLoadFolderContent(node: TreeOption) {
  const folderId = Number(node.key)
  if (!Number.isNaN(folderId)) {
    await loadFolderContent(folderId)
  }
}
function handleCheckable(node: TmNode) {
  const { item } = node.rawNode as { item: TreeViewElement }
  if (!item || item.kind === "file") {
    return false
  }

  return true
}

// Add a function to load folder content
async function loadFolderContent(folderId: number) {
  // Skip if already loaded or currently loading
  if (loadedFolderContents.value[folderId] || folderLoadingStates.value[folderId]) {
    return
  }

  try {
    // Set loading state for this folder
    folderLoadingStates.value[folderId] = true

    // Find the folder in our array
    const folderIndex = starredFolders.value.findIndex(f => f.id === folderId)
    if (folderIndex === -1)
      return

    // Set folder loading state
    starredFolders.value[folderIndex].isLoading = true

    // Load stars for this folder
    const starsResult = await getStars({ folder_id: folderId, page: 1, page_size: 50 })

    if (starsResult && starsResult.stars) {
      // Convert stars to tree elements
      const starElements: TreeViewElement[] = starsResult.stars.map(({ id, resource_type, resource_id, resource_summary }) => ({
        id: String(id),
        filename: resource_summary,
        kind: "file",
        status: "success",
        isEditable: false,
        isSelectable: false,
        path: `${folderId}/${id}`,
        value: resource_id, // Store the original star data
        icon: markRaw(resource_type === StarResourceType.Protocol ? ProtocolIcon : resource_type === StarResourceType.Answer ? AnswerIcon : QuestionIcon),
      }))

      // Update the folder with children
      starredFolders.value[folderIndex].children = starElements.map(element => ({
        id: Number(element.id),
        resourceType: element.icon === ProtocolIcon ? StarResourceType.Protocol : element.icon === AnswerIcon ? StarResourceType.Answer : StarResourceType.Question,
        resourceId: element.value as string,
        resourceName: element.filename,
        folderIds: [folderId],
        createdAt: new Date().toISOString(),
      }))
    }

    // Mark as loaded
    loadedFolderContents.value[folderId] = true
  }
  catch (error) {
    message.error((error as Error).message)
  }
  finally {
    folderLoadingStates.value[folderId] = false

    // Find the folder in our array (again in case the array changed)
    const folderIndex = starredFolders.value.findIndex(f => f.id === folderId)
    if (folderIndex !== -1) {
      starredFolders.value[folderIndex].isLoading = false
    }
  }
}
const { routerPushByKey } = useRouterPush()

async function handleOpenItem(item: TreeViewElement) {
  const { id, kind, path } = item
  if (kind === "directory" || !path) {
    return
  }
  const [folderId] = path.split("/")

  const target = starredFolders.value.find(f => f.id === Number(folderId))?.children?.find(c => c.id === Number(id)) as unknown as StarItem
  if (!target) {
    return
  }
  const { resourceType, resourceId } = target
  if (resourceType === StarResourceType.Protocol) {
    const { data } = await getProtocolInfo(resourceId, undefined, false)
    if (data) {
      const { lab, project, uid } = data
      routerPushByKey("protocol-detail", { params: { labUid: lab.uid, projectUid: project.uid, protocolUid: uid } })
    }
  }
  else if (resourceType === StarResourceType.Question) {
    const data = await getQuestionDetail(resourceId)
    if (data) {
      const { protocol_id, id } = data
      if (!protocol_id || !id) {
        return
      }

      const { data: protocolData } = await getProtocolInfo(protocol_id, undefined, false)
      if (protocolData) {
        const { lab, project, uid } = protocolData
        routerPushByKey("protocol-discussion-detail", { params: { labUid: lab.uid, projectUid: project.uid, protocolUid: uid, questionId: id } })
      }
    }
  }
}

function handleItemAction(item: TreeViewElement): Action[] | null {
  const { id, kind } = item
  if (kind === "directory") {
    if (Number(id) === defaultFolderId.value) {
      return []
    }
    return null
  }
  return [
    {
      id: "open",
      icon: OpenIcon,
      handler: () => handleOpenItem(item),
    },
    {
      id: "delete",
      icon: TrashIcon,
      handler: () => handleContextMenuSelect("delete", item),
      confirmMessage: item => `Are you sure you want to delete "${item.filename}"?`,
    },
  ]
}

watch(
  () => props.starred,
  () => {
    starStateOverride.value = null
  },
)

watch(
  isShown,
  (shown) => {
    if (shown) {
      emits("modal:open")
    }
    else {
      isManagingExistingStar.value = false
      emits("modal:close")
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  clearUndoUnstarContext()
})
</script>

<style scoped lang="sass">
:deep(.n-base-selection)
  --n-height: 40px!important
  --n-color: #F7F8F9!important
  border-radius: 8px

.border-b
  border-bottom: 1px solid #eaecf0

:deep(.star-trigger-button.is-starred)
  background-color: #FFF8E6 !important
  border: 1px solid #F2CF66 !important
  color: #8A5A00 !important

:deep(.star-trigger-button.is-starred:hover)
  background-color: #FDEFC8 !important
  border-color: #E3B341 !important
  color: #6F4600 !important

:deep(.star-trigger-button.is-starred .n-icon)
  color: #E3B341 !important
</style>

<template>
  <div class="h-full w-full flex flex-col">
    <input
      ref="localUploadInputRef"
      type="file"
      multiple
      class="hidden"
      @change="handleLocalFileChange"
    >

    <div class="relative w-full flex-center gap-1 px-3">
      <span class="mr-auto select-none whitespace-nowrap">File Explorer</span>
      <tooltip-button
        v-for="action in actions"
        :key="action.tooltip"
        class="text-#666"
        :button-props="buttonProps"
        :tooltip="action.tooltip"
        :icon="action.icon"
        :disabled="action.disabled"
        :tooltip-disabled="false"
        @click="action.handler"
      />
    </div>
    <div class="w-full flex flex-col justify-start px-0" @click="handleClearSelected">
      <file-tree ref="fileTreeRef" :elements="fileData" @click.stop />
    </div>

    <div class="mt-auto w-full p-3">
      <n-upload
        ref="uploadRef"
        :show-file-list="false"
        :max="1"
        accept=".zip,application/zip"
        abstract
        :custom-request="customRequest"
      >
        <tooltip-button
          :tooltip="isUploading ? 'Processing...' : 'Import Protocol ZIP file'"
          type="primary"
          class="w-full"
          :loading="isUploading"
          @click="handleUploadClick"
        >
          <template #icon>
            <n-icon>
              <icon-tabler-upload />
            </n-icon>
          </template>
          {{ isUploading ? 'Processing...' : 'Import ZIP' }}
        </tooltip-button>
      </n-upload>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { UploadCustomRequestOptions, UploadFileInfo, UploadInst } from "naive-ui"

import type { FileSystemItem } from "../../types"
import { saveProjectData } from "@airalogy/components/monaco-editor/utils"

import TooltipButton from "@airalogy/components/tooltip-button.vue"
import { downloadAs } from "@airalogy/shared/utils"
import { useRouteQuery } from "@vueuse/router"
import CloudDownload from "~icons/ion/cloud-download"
import FileAdd from "~icons/tabler/file-plus"
import FolderAdd from "~icons/tabler/folder-plus"
import UploadIcon from "~icons/tabler/upload"

import { useDialog, useMessage } from "naive-ui"
import { nanoid } from "nanoid"
import { storeToRefs } from "pinia"
import { useFileUpload } from "../../composables/useFileUpload"
import { PENDING_DIRECTORY, PENDING_FILE, useUploadFileDataStore } from "../../store/uploadFileDataStore"
import { useWebContainerStore } from "../../store/webContainerStore"
import { isDirectory } from "../../utils"
import { findById, findParent } from "../../utils/file-tree"
import FileTree from "../file-tree/index.vue"

const uploadRef = ref<UploadInst | null>(null)
const localUploadInputRef = ref<HTMLInputElement | null>(null)
const uploadFileDataStore = useUploadFileDataStore()
const { addFileOrFolder } = uploadFileDataStore
const { fileData, selected, rootPath } = storeToRefs(uploadFileDataStore)

const { handleUpload, isUploading, compressFiles, uploadLocalFiles } = useFileUpload()

// Reference to the FileTree component to access its expandedKeys
const fileTreeRef = ref<InstanceType<typeof FileTree> | null>(null)
const isReadOnly = injectLocal<Ref<boolean>>("isEditorReadOnly", ref(false))

const buttonProps = {
  quaternary: true,
  circle: true,
  size: "small",
  color: "#white",
} as const

const actions = computed(() => {
  const disabled = isReadOnly.value

  return [
    {
      tooltip: "Download as ZIP",
      icon: CloudDownload,
      handler: handleDownload,
    },
    {
      tooltip: disabled ? "You can't upload files in read only mode" : "Upload local files",
      icon: UploadIcon,
      handler: handleLocalUploadClick,
      disabled,
    },
    {
      tooltip: disabled ? "You can't add new folder in read only mode" : "Add new folder",
      icon: FolderAdd,
      handler: handleAddFolder,
      disabled,
    },
    {
      tooltip: disabled ? "You can't add new file in read only mode" : "Add new file",
      icon: FileAdd,
      handler: handleAddFile,
      disabled,
    },
  ]
})

const message = useMessage()

async function handleDownload() {
  try {
    if (!fileData.value) {
      message.error("No files to download")
      return
    }

    const result = await compressFiles()
    if (!result) {
      return
    }

    downloadAs(result.file, "protocol.zip")
  }
  catch (error) {
    console.error("Error downloading files:", error)
  }
}

function joinPath(basePath: string, filename: string) {
  return [basePath, filename].filter(Boolean).join("/")
}

function getTargetDirectory() {
  if (!fileData.value || !selected.value) {
    return null
  }

  const selectedItem = findById(fileData.value, selected.value)
  if (selectedItem && isDirectory(selectedItem)) {
    return selectedItem
  }

  return findParent(fileData.value, selected.value, true)
}

function expandTargetDirectory(parent: { id: string } | null) {
  if (parent && fileTreeRef.value) {
    fileTreeRef.value.expandNode(parent.id)
  }
}

function handleAddFolder() {
  const parent = getTargetDirectory()

  expandTargetDirectory(parent)

  addFileOrFolder(
    {
      kind: "directory",
      name: PENDING_DIRECTORY,
      parent,
      status: "pending",
      id: nanoid(),
      children: [],
      path: joinPath(parent?.path || rootPath.value, PENDING_DIRECTORY),
    },
  )
}

function handleAddFile() {
  const parent = getTargetDirectory()

  expandTargetDirectory(parent)

  addFileOrFolder(
    {
      kind: "file",
      name: PENDING_FILE,
      parent,
      status: "pending",
      id: nanoid(),
      content: "",
      path: joinPath(parent?.path || rootPath.value, PENDING_FILE),
    },
  )
}

async function customRequest({
  file,
  onFinish,
}: UploadCustomRequestOptions) {
  await handleUploadData(file)
  onFinish()
}

function handleUploadClick() {
  uploadRef.value?.openOpenFileDialog()
}

function handleLocalUploadClick() {
  localUploadInputRef.value?.click()
}

async function handleLocalFileChange(event: Event) {
  const input = event.target as HTMLInputElement | null
  const files = input?.files ? Array.from(input.files) : []

  if (files.length === 0) {
    return
  }

  const parent = getTargetDirectory()
  expandTargetDirectory(parent)
  await uploadLocalFiles(files, parent)

  if (input) {
    input.value = ""
  }
}

const router = useRouter()
const route = useRoute()
const { clearFileData } = uploadFileDataStore
const webContainerStore = useWebContainerStore()
const { initWebContainer } = webContainerStore

function handleClearFileData(projectId: string) {
  try {
    clearFileData(true, projectId)
  }
  catch (error) {
    console.error(error)
  }
}
const dialog = useDialog()
const packageId = useRouteQuery<string>("package_id")

async function wrappedSaveProjectData(id: string, data: FileSystemItem[]) {
  try {
    await saveProjectData(id, data, uploadFileDataStore.uploadProtocolPackage)
  }
  catch (error) {
    console.error("Error saving project data:", error)
  }
}
async function handleUploadData(file: UploadFileInfo) {
  if (file.type === "application/zip" || file.name.endsWith(".zip")) {
    dialog.warning({
      title: "Warning",
      content: "This will clear the current project and start a new one. Are you sure you want to continue?",
      positiveText: "Yes",
      negativeText: "No",
      onPositiveClick: async () => {
        await handleClearFileData(packageId.value)
        await handleUpload(file)
        const id = nanoid()

        await router.replace({
          ...route,
          query: {
            ...route.query,
            package_id: id,
          },
        })

        if (fileData.value) {
          await saveProjectData(id, fileData.value, uploadFileDataStore.uploadProtocolPackage)
          await initWebContainer(id, fileData, uploadFileDataStore.rootPath, wrappedSaveProjectData)
        }
      },
    })
  }
  else {
    message.warning("Only protocol ZIP files can be imported here. Use the upload action above for local images and attachments.")
  }
}
function handleClearSelected() {
  selected.value = ""
}
</script>

<style lang="scss" scoped>
.tooltip-button {
  --n-color-hover: rgba(255, 255, 255, 0.09);
  --n-color: transparent;
  --n-color-pressed: rgba(255, 255, 255, 0.13);

  &:hover {
    color: white;
  }
}
</style>

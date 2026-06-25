<template>
  <n-input
    v-if="props.status === 'pending' || props.status === 'error'"
    ref="inputRef"
    v-model:value="pendingname"
    :size="props.size"
    :theme-overrides="{ borderRadius: '4px', heightTiny: '20px', heightSmall: '22px', paddingSmall: '0 4px' }"
    autofocus
    :status="props.status === 'error' ? 'error' : undefined"
    @keyup.enter="throttledChangeStatus"
    @keyup.esc="handleCancel"
    @blur="throttledChangeStatus"
  />
  <n-ellipsis v-else>
    {{ props.name }}
  </n-ellipsis>
</template>

<script setup lang="ts">
import type { InputInst } from "naive-ui"
import type { DirectoryInterface, FileSystemItem } from "../../../types"
import type { WebContainer } from "../../../types/fileSystem"
import { createDir, createFile } from "@airalogy/components/monaco-editor/utils/webcontainer"
import { isPending, prepareName, useUploadFileDataStore } from "../../../store/uploadFileDataStore"
import { useWebContainerStore } from "../../../store/webContainerStore"
import { isDirectory, isFile } from "../../../utils"

interface Props {
  name: string
  id: string
  path: string
  kind: "directory" | "file"
  status: "init" | "modified" | "uploaded" | "error" | "pending" | "success"
  updateItem?: (id: string, updatedProperties: Partial<DirectoryInterface>) => boolean
  size?: "tiny" | "small" | "medium" | "large"
}

const props = withDefaults(defineProps<Props>(), {
  size: "tiny",
  name: "",
})

const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "update:properties", updatedProperties: Partial<DirectoryInterface>): void
}

const { removeFileById, updateFileItem } = useUploadFileDataStore()
const containerStore = useWebContainerStore()
const inputRef = ref<InputInst | null>(null)

const pendingname = ref(prepareName(props.name))

async function handleUpdateItem(id: string, updatedProperties: Partial<DirectoryInterface>) {
  let result: boolean | FileSystemItem = false
  if (props.updateItem) {
    result = props.updateItem(id, updatedProperties)
  }
  else {
    result = await updateFileItem(id, updatedProperties, true)
  }

  emit("update:properties", updatedProperties)

  return result
}

async function handleCancel() {
  const { path, name } = props

  if ((pendingname.value === "" && isPending(path)) || isPending(name)) {
    removeFileById(props.id)
    pendingname.value = ""
  }
  else if (name) {
    pendingname.value = name
    handleUpdateItem(props.id, {
      status: "success",
    })
  }
}

async function handleChangeStatus() {
  if (pendingname.value === "") {
    handleCancel()
    return
  }

  const { path, name: prevName } = props
  const normalizedPrevName = prepareName(prevName)
  const normalizedPath = prepareName(path)

  // Create new file/directory
  if (normalizedPrevName === "") {
    const updatePath = normalizedPath + pendingname.value

    const result = await handleUpdateItem(props.id, {
      name: pendingname.value,
      path: updatePath,
      status: "pending",
      isEditable: true,
      isSelectable: props.kind === "file",
    })

    if (!result) {
      return
    }

    if (containerStore.webContainerInstance) {
      if (isFile(props)) {
        await createFile(updatePath, containerStore.webContainerInstance as WebContainer)
      }
      else if (isDirectory(props)) {
        await createDir(updatePath, containerStore.webContainerInstance as WebContainer)
      }
    }

    await handleUpdateItem(result === true ? props.id : result.id, {
      status: "success",
    })
  }
  else if (normalizedPrevName === pendingname.value) {
    handleUpdateItem(props.id, {
      status: "success",
    })
  }
  else {
    // Rename existing file/directory
    const updatePath = normalizedPath.replace(prevName, "") + pendingname.value

    if (containerStore.webContainerInstance) {
      await containerStore.webContainerInstance.fs.rename(props.path, updatePath)
    }

    handleUpdateItem(props.id, {
      name: pendingname.value,
      path: updatePath,
      status: "success",
      isEditable: true,
      isSelectable: props.kind === "file",
    })
  }
}

const throttledChangeStatus = useThrottleFn(handleChangeStatus, 100)

watch(inputRef, (inst) => {
  if (inst) {
    inst.focus()
  }
}, { immediate: true })
</script>

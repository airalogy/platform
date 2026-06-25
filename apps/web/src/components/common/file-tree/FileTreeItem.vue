<template>
  <n-input
    v-if="props.status === 'pending'"
    ref="inputRef"
    v-model:value="pendingFileName"
    :size="props.size"
    :theme-overrides="{ borderRadius: '4px', heightMedium: '32px', heightTiny: '20px', heightSmall: '22px', paddingSmall: '0 4px' }"
    autofocus
    @keyup.enter="handleChangeStatus"
    @keyup.esc="handleCancel"
    @blur="handleChangeStatus"
  />
  <div v-else class="flex items-center">
    <n-ellipsis>
      {{ props.filename }}
    </n-ellipsis>
  </div>
</template>

<script setup lang="ts">
import type { InputInst } from "naive-ui"

interface Props {
  filename: string
  id: string
  path?: string
  kind?: "directory" | "file"
  status: "init" | "modified" | "uploaded" | "error" | "pending" | "success"
  size?: "tiny" | "small" | "medium" | "large"
}

interface UpdatedProperties {
  filename?: string
  path?: string
  status?: Props["status"]
  isEditable?: boolean
  isSelectable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  size: "tiny",
  filename: "",
  kind: "file",
  path: "",
})

const emit = defineEmits<{
  (e: "update:properties", updatedProperties: UpdatedProperties): void
}>()

const inputRef = ref<InputInst | null>(null)
const pendingFileName = ref(props.filename)

function prepareName(name: string): string {
  return name.trim()
}

async function handleCancel() {
  const { path, filename } = props

  if ((pendingFileName.value === "" && path === "") || filename === "") {
    pendingFileName.value = ""
    emit("update:properties", {
      filename: "",
      status: "success",
    })
  }
  else if (filename) {
    pendingFileName.value = filename
    emit("update:properties", {
      status: "success",
    })
  }
}

async function handleChangeStatus() {
  if (pendingFileName.value === "") {
    handleCancel()
    return
  }

  const { path, filename: prevFilename } = props
  const normalizedPrevFilename = prepareName(prevFilename)
  const normalizedPath = prepareName(path || "")

  // Create new file/directory
  if (normalizedPrevFilename === "") {
    const updatePath = normalizedPath + pendingFileName.value

    emit("update:properties", {
      filename: pendingFileName.value,
      path: updatePath,
      status: "success",
      isEditable: true,
      isSelectable: props.kind === "file",
    })
  }
  else if (normalizedPrevFilename === pendingFileName.value) {
    emit("update:properties", {
      status: "success",
    })
  }
  else {
    // Rename existing file/directory
    const updatePath = normalizedPath.replace(prevFilename, "") + pendingFileName.value

    emit("update:properties", {
      filename: pendingFileName.value,
      path: updatePath,
      status: "success",
      isEditable: true,
      isSelectable: props.kind === "file",
    })
  }
}

watch(inputRef, (inst) => {
  if (inst) {
    inst.focus()
  }
}, { immediate: true })
</script>

<template>
  <menu-bar-item
    :enable-tooltip="enableTooltip"
    tooltip="Insert Image"
    :disabled="props.disabled"
    :icon="Photo"
  >
    <template #default="{ themeOverrides, icon }">
      <n-upload
        v-model:file-list="fileList"
        :custom-request="customRequest"
        :show-file-list="false"
        accept="image/*"
        :disabled="props.disabled"
        :multiple="false"
        @change="handleChange"
      >
        <n-button
          quaternary
          type="default"
          size="medium"
          :theme-overrides="themeOverrides"
          :disabled="props.disabled"
        >
          <template v-if="icon" #icon>
            <n-icon :component="icon" />
          </template>
        </n-button>
      </n-upload>
    </template>
  </menu-bar-item>
</template>

<script setup lang="ts">
import type { Editor } from "@tiptap/vue-3"
import type { UploadCustomRequestOptions, UploadFileInfo } from "naive-ui"
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
import { useClosableMessage } from "@airalogy/composables"
import Photo from "~icons/tabler/photo"

defineOptions({ name: "InsertImageItem" })

const props = defineProps<IProps>()

interface IProps {
  editor: Editor
  disabled: boolean
}

const message = useClosableMessage()

const enableTooltip = inject("enableTooltip", true)

const fileList = ref<UploadFileInfo[]>([])
const imageExtension = computed(() => props.editor.extensionManager.extensions.find(extension => extension.name === "airalogyImage"))

function handleChange(data: { fileList: UploadFileInfo[] }) {
  // Clear file list after upload completes to prepare for next upload
  if (data.fileList.every(file => file.status === "finished" || file.status === "error")) {
    setTimeout(() => {
      fileList.value = []
    }, 100)
  }
}

async function customRequest(options: UploadCustomRequestOptions) {
  if (!options.file.file) {
    options.onError?.()
    return
  }

  try {
    const uploadFn = imageExtension.value?.options.uploadFn
    if (!uploadFn) {
      message.error("Upload function not found")
      options.onError?.()
      return
    }

    const res = await uploadFn(options.file.file, props.editor, imageExtension.value.options)

    if (res) {
      if (typeof res === "string") {
        props.editor.commands.setImages([{
          src: res,
          id: res,
          name: options.file.file.name,
          alt: options.file.file.name,
          filename: options.file.file.name,
        }])
      }
      else {
        const { id, filename, src, airalogyId } = res

        props.editor.commands.setImages([{
          src,
          id: String(airalogyId || id || ""),
          name: filename,
          alt: filename,
          filename,
        }])
      }

      message.success("Image upload succeeded.", { duration: 2000 })
      options.onFinish?.()
    }
    else {
      options.onError?.()
    }
  }
  catch (error) {
    console.error("Image upload failed:", error)
    message.error("Image upload failed")
    options.onError?.()
  }
}
</script>

<style lang="scss">
</style>

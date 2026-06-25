<template>
  <menu-bar-item
    :command="openAddImageDialog"
    :enable-tooltip="enableTooltip"
    tooltip="Add Image"
    :disabled="props.disabled"
    :icon="Photo"
  >
    <template #default="{ handleClick, themeOverrides, icon }">
      <n-popconfirm
        v-model:show="addImageDialogVisible"
        title="Add Image"
        custom-class="tiptap-edit-image-dialog"
        placement="bottom"
        :show-icon="false"
        style="min-width: 380px"
        :disabled="props.disabled"
      >
        <n-form
          :model="imageAttrs"
          label-placement="top"
          size="small"
          class="flex-1 pt-2"
          :show-feedback="false"
        >
          <n-form-item label="Airalogy image ID" path="id">
            <n-input
              v-model:value="imageAttrs.id"
              placeholder="Enter Airalogy image ID"
              autocomplete="off"
            />
          </n-form-item>

          <n-form-item label="Image name" path="name" class="my-2">
            <n-input
              v-model:value="imageAttrs.name"
              placeholder="Name in ![name]()"
              autocomplete="off"
            />
          </n-form-item>

          <n-divider class="!my-3" />

          <n-form-item label="Upload" path="alt" class="my-2">
            <n-upload
              v-model:file-list="fileListRef"
              :custom-request="customRequest"
              :show-file-list="false"
              accept="image/*"
              :multiple="false"
            >
              <n-button size="small">
                <template #icon>
                  <n-icon><icon-tabler-upload /></n-icon>
                </template>
                Upload Image
              </n-button>
            </n-upload>
          </n-form-item>
        </n-form>

        <template #trigger>
          <n-button
            quaternary
            type="default"
            size="medium"
            :theme-overrides="themeOverrides"
            :disabled="props.disabled"
            @click="handleClick"
          >
            <template v-if="icon" #icon>
              <n-icon :component="icon" />
            </template>
          </n-button>
        </template>

        <template #action>
          <div class="flex gap-2">
            <n-button size="small" @click="closeAddImageDialog">
              Cancel
            </n-button>
            <n-button
              type="primary"
              size="small"
              :disabled="!(imageAttrs.id && imageAttrs.name)"
              @mousedown.prevent
              @click="addImage"
            >
              Add Image
            </n-button>
          </div>
        </template>
      </n-popconfirm>
    </template>
  </menu-bar-item>
</template>

<script setup lang="ts">
import type { Editor } from "@tiptap/vue-3"
import type { UploadCustomRequestOptions, UploadFileInfo } from "naive-ui"
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"
// import { postAddAttachments } from "@airalogy/components/service/api/attachments"
// import { baseURL } from "@airalogy/components/service/request"
// import { useProtocolInfoStore } from "@airalogy/components/views/project-protocols/hooks/useProtocolInfo"
import { useClosableMessage } from "@airalogy/composables"
import Photo from "~icons/tabler/photo"

defineOptions({ name: "InsertImageItem" })

const props = defineProps<IProps>()

interface IProps {
  editor: Editor
  disabled: boolean
}

interface ImageAttributes {
  id: string
  name: string
}

const fileListRef = ref<UploadFileInfo[]>([])
const message = useClosableMessage()

const enableTooltip = inject("enableTooltip", true)
const imageAttrs = ref<ImageAttributes>({
  id: "",
  name: "",
})

const addImageDialogVisible = ref(false)

watch(addImageDialogVisible, () => {
  imageAttrs.value = { id: "", name: "" }
})

function openAddImageDialog() {
  addImageDialogVisible.value = true
}

function closeAddImageDialog() {
  addImageDialogVisible.value = false
}

// function getImageUrl(id: string): string {
//   return `${baseURL}/attachments/${id}`
// }

function addImage() {
  props.editor.commands.setImages([
    {
      src: (props.editor.options as any).getImageUrl?.(imageAttrs.value.id) || "",
      id: imageAttrs.value.id,
      alt: imageAttrs.value.name,
    },
  ])

  closeAddImageDialog()
}

const imageExtension = computed(() => {
  return props.editor.options.extensions.find(ext => ext.name === "")
})

async function customRequest(options: UploadCustomRequestOptions) {
  if (!options.file.file || !imageExtension.value) {
    options.onError?.()
    return
  }

  try {
    const { options: extensionOptions } = imageExtension.value
    const res = await extensionOptions?.uploadFn?.(options.file.file, props.editor, extensionOptions)

    if (res) {
      if (typeof res === "string") {
        props.editor.commands.setImages([{
          src: res,
          id: res,
          alt: options.file.file.name,
          filename: options.file.file.name,
        }])
      }
      else {
        const { id, filename, src, airalogyId } = res

        props.editor.commands.setImages([{
          src,
          id: String(airalogyId || id || ""),
          alt: filename,
          filename,
        }])
      }

      message.success("Image upload succeeded.", { duration: 2000 })
      options.onFinish?.()
      closeAddImageDialog()
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
.tiptap-edit-image-dialog {
  .n-popconfirm-action {
    margin-top: 0;
  }
}
</style>

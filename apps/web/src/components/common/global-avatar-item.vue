<template>
  <div class="avatar-upload relative">
    <n-upload
      v-if="showEdit"
      abstract
      accept="image/jpeg,image/png"
      :action="`${baseURL}/attachments`"
      :headers="{ 'auth-token': authStore.token }"
      :show-file-list="false"
      :default-upload="false"
      :file-list="fileListRef"
      @change="handleAvatarChange"
    >
      <n-spin :show="isUploading" class="relative h-fit w-fit">
        <!-- Avatar with Edit Button -->
        <n-avatar
          v-bind="props"
          color="white"
          :src="previewImageUrlRef || props.src"
        />

        <n-upload-trigger #="{ handleClick }" abstract>
          <div v-if="showEdit" class="absolute bottom-1/8 left-0 opacity-60 hover:opacity-100">
            <n-dropdown
              trigger="click"
              :options="dropdownOptions"
              @select="(key: string) => handleSelect(key, handleClick)"
            >
              <n-button size="small" type="default" class="b-1 rounded-md !bg-white">
                <span class="text-sm">{{ $t("common.edit") }}</span>
                <template #icon>
                  <n-icon size="16">
                    <icon-ion-pencil-outline />
                  </n-icon>
                </template>
              </n-button>
            </n-dropdown>
          </div>
        </n-upload-trigger>
      </n-spin>
    </n-upload>
    <n-avatar v-else v-bind="props" />
  </div>
</template>

<script setup lang="tsx">
import type { AvatarProps, DropdownOption, UploadFileInfo } from "naive-ui"
import { useBoolean } from "@/composables"
import { baseURL } from "@/service/request"
import { useAuthStore } from "@/store/modules/auth"
import { $t } from "@airalogy/shared/locales"
import { computed } from "vue"

interface IProps {
  src?: AvatarProps["src"]
  size?: AvatarProps["size"]
  round?: boolean
  showEdit?: boolean
  file?: UploadFileInfo | null
}

interface IEmits {
  (e: "update:file", file: UploadFileInfo | null): void
}

const props = withDefaults(defineProps<IProps>(), {
  fallbackSrc: "images/avatar_default.svg",
  src: "images/avatar_default.svg",
  round: true,
  showEdit: false,
})

const emit = defineEmits<IEmits>()
const authStore = useAuthStore()

const fileListRef = ref<UploadFileInfo[]>([])
const previewImageUrlRef = ref("")
const { bool: isUploading, setTrue: startLoading, setFalse: endLoading } = useBoolean()
const avatarRef = useVModel(props, "file", emit)

const dropdownOptions = computed<DropdownOption[]>(() => ([
  {
    label: $t("common.uploadAvatar"),
    key: "upload",
    icon: () => (
      <n-icon size="16">
        <icon-ion-image-outline />
      </n-icon>
    ),
  },
  {
    label: $t("common.removeAvatar"),
    key: "remove",
    icon: () => (
      <n-icon size="16">
        <icon-ion-trash-outline />
      </n-icon>
    ),
  },
]))

function handleSelect(key: string, handleClick: () => void) {
  switch (key) {
    case "upload":
      handleClick()
      break
    case "remove":
      handleRemovePhoto()
      break
  }
}

function handleRemovePhoto() {
  previewImageUrlRef.value = ""
}

function handleAvatarChange(option: {
  file: UploadFileInfo
  fileList: UploadFileInfo[]
  event?: Event
}) {
  const { file, fileList } = option
  fileListRef.value = fileList

  if (file.status === "removed") {
    avatarRef.value = null

    return
  }

  if (file.file) {
    const reader = new FileReader()

    reader.readAsDataURL(file.file)
    reader.addEventListener(
      "load",
      () => {
        previewImageUrlRef.value = reader.result as string
      },
      { once: true },
    )
    avatarRef.value = file
  }
  else {
    avatarRef.value = null
  }
}
</script>

<style scoped lang="sass">

</style>

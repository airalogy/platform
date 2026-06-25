<template>
  <div>
    <n-button
      :bordered="false"
      class="scale-80"
      :theme-overrides="{
        colorHover: 'rgba(36,82,148,0.1)',
        colorPressed: 'rgba(36,82,148,0.2)',
        colorFocus: 'rgba(36,82,148,0.1)',
        textColor: '#A1A4AF',
        textColorHover: '#6A6C73',
        textColorPressed: '#6A6C73',
        textColorFocus: '#6A6C73',
        rippleColor: '#245294',
      }"
      v-bind="props.buttonProps"
      @click.stop="showModal"
    >
      <template #icon>
        <edit-icon />
      </template>
    </n-button>
    <n-modal
      :show="isShown"
      preset="card"
      size="huge"
      class="w-160"
      header-class="border-b !py-5 !px-6"
      content-class="!px-6 !py-6"
      :mask-closable="false"
      @update:show="setModalStatus"
    >
      <template #header>
        Edit lab
      </template>
      <div class="max-h-80vh w-full overflow-x-visible overflow-y-auto">
        <n-form ref="formRef" :model="model" :rules="rules" size="large">
          <n-form-item label="Upload logo" path="logo">
            <form-upload-file
              ref="logoUploadRef"
              :upload-props="{ accept: 'image/*' }"
              @update:file="handleSelectLogo"
              @uploaded:file="handleUploadedLogo"
            />
          </n-form-item>
          <n-form-item label="Lab display name" path="displayName">
            <n-input
              v-model:value="model.displayName"
              type="text"
              :maxlength="30"
              required
              show-count
              placeholder="Enter lab display name"
            />
          </n-form-item>
          <n-form-item label="Description" path="description">
            <n-input
              v-model:value="model.description"
              type="textarea"
              :maxlength="128"
              :autosize="true"
              :max-rows="10"
              show-count
              placeholder="Describe the lab"
            />
          </n-form-item>
          <!-- <n-form-item label="Select type" path="type">
            <n-radio-group v-model:value="model.type">
              <n-radio
                v-for="type in typeList"
                :key="type.value"
                :value="type.value"
                size="small"
                class="capitalize first:mr-4"
              >
                {{ type.label }}
              </n-radio>
            </n-radio-group>
          </n-form-item> -->
        </n-form>
        <div class="flex items-center justify-end">
          <n-button size="medium" class="mr-4" :disabled="submitting" @click="handleCancel">
            Cancel
          </n-button>
          <n-button
            size="medium"
            type="primary"
            :disabled="loading"
            :loading="submitting"
            @click="handleConfirm"
          >
            Confirm
          </n-button>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { ICustomSelectOption } from "@/components/common/global-add-member.vue"

import type { SelectOption } from "naive-ui/es/select"
import { useBoolean, useFormRules, useLoading, useNaiveForm, useShowModal } from "@/composables"
import { putLabInfo } from "@/service/api/labs"
import { getPinyin } from "@/utils/zhCharToPinyin"

import { useClosableMessage } from "@airalogy/composables"
import { DISPLAY_NAME_TRIM } from "@airalogy/shared/constants/reg"
import { isEqual } from "lodash-es"
import { type UploadFileInfo, type UploadInst, useDialog } from "naive-ui"
import { type ButtonProps, NButton } from "naive-ui/es/button"

interface IProps {
  buttonType?: "text" | "ghost"
  showIcon?: boolean
  buttonProps?: ButtonProps & { class?: string }
  item?: Api.Lab.LabInfo | null
}
const props = withDefaults(defineProps<IProps>(), {
  buttonType: "ghost",
  showIcon: false,
  buttonProps: () => ({}),
  item: undefined,
})

const emits = defineEmits<IEmits>()

interface FormModel {
  name?: string
  displayName?: string
  description?: string
  type?: Api.Lab.GroupType
  members?: string
  logo?: string
}

const { isShown, showModal, hideModal, setModalStatus } = useShowModal()
const { bool: isShowMenu, setFalse: hideMenu, setTrue: showMenu } = useBoolean()
const { defaultRequiredRule } = useFormRules()
const { formRef, validate } = useNaiveForm()

const typeList: { label: string, value: FormModel["type"] }[] = [
  { label: "private", value: 1 },
  { label: "public", value: 2 },
]

interface IEmits {
  (e: "modal:edit-lab", val: Api.Lab.LabItem): void
  (e: "modal:close"): void
  (e: "modal:open"): void
}

const rules: Partial<Record<keyof FormModel, App.Global.FormRule[]>> = {
  displayName: [
    defaultRequiredRule,
    {
      min: 1,
      max: 40,
      message: "Lab display name must be between 1 and 40 characters long",
      trigger: ["change", "blur"],
    },
    {
      validator: (rule, value, callback) => {
        if (/^[_-]|[_-]$/.test(value)) {
          return new Error("Lab display name should not start or end with a hyphen")
        }
        if (/[_-]{2,}/.test(value)) {
          return new Error("Hyphens cannot appear consecutively")
        }
        return true
      },
      trigger: ["change", "blur"],
    },
  ],
  name: [
    defaultRequiredRule,
    {
      min: 1,
      max: 40,
      message: "Lab name must be between 1 and 40 characters long",
      trigger: ["change", "blur"],
    },
    {
      pattern: /^[\w-]*$/,
      message: "Lab name can only contain letters (a-z, A-Z), numbers (0-9), or hyphens (_-)",
      trigger: ["change", "blur"],
    },
    {
      validator: (rule, value, callback) => {
        if (/^[_-]|[_-]$/.test(value)) {
          return new Error("Lab name should not start or end with a hyphen")
        }
        if (/[_-]{2,}/.test(value)) {
          return new Error("Hyphens cannot appear consecutively")
        }
        return true
      },
      trigger: ["change", "blur"],
    },
  ],
  type: [defaultRequiredRule],
}

const memberOptions = ref<SelectOption[]>([])
const { loading, startLoading, endLoading } = useLoading()

const initValue = computed(
  (): FormModel => ({
    displayName: props.item?.name,
    description: props.item?.description,
    type: props.item?.type,
    members: undefined,
    logo: props.item?.logo || undefined,
  }),
)

const model = ref<FormModel>({ ...initValue.value })

function handleClearOption() {
  hideMenu()
  setTimeout(() => (memberOptions.value = []), 200)
}

function restoreModel() {
  model.value = { ...initValue.value }

  memberOptions.value = []

  formRef.value?.restoreValidation()
}

const membersRef = ref<ICustomSelectOption[]>([])
function handleUpdateSelect(val: ICustomSelectOption[]) {
  membersRef.value = val
}

const route = useRoute()
const { loading: submitting, startLoading: startSubmit, endLoading: endSubmit } = useLoading()

const dialog = useDialog()
const message = useClosableMessage()

async function handleCancel() {
  hideModal()

  await nextTick(() => {
    restoreModel()
  })
}

async function handleConfirm() {
  await validate()

  const labId = props.item?.id
  if (!labId || Array.isArray(labId)) {
    return
  }

  const isNotChanged = isEqual(model.value, initValue.value)

  if (isNotChanged) {
    dialog.warning({
      title: "Lab info not changed",
      closable: false,
      positiveText: "Close",
      positiveButtonProps: { size: "medium" },
      negativeText: "Cancel",
      negativeButtonProps: { size: "medium" },
      onPositiveClick: () => {
        hideModal()
      },
    })
    return
  }
  startSubmit()

  const { description, displayName, type, logo } = model.value
  const { data, error } = await putLabInfo(labId, {
    description,
    name: displayName,
    type,
    logo,
  })

  endSubmit()

  if (error) {
    // NOPE
  }
  else {
    message.success("Successfully changed lab info.")
    emits("modal:edit-lab", data)
    hideModal()
  }
}

async function handleUpdateName(name: string) {
  const trimmed = name.trim()
  const pinyin = await getPinyin(trimmed)
  const newName = pinyin
    .replaceAll(/\W/g, "_")
    .replace(DISPLAY_NAME_TRIM, "")
    .replace(/[_-]{2,}/g, "_")
  model.value.name = newName
}

const logoUploadRef = ref<{ uploadRef: UploadInst } | null>(null)
const fileRef = ref<File | null>(null)

function handleSelectLogo(fileInfo: {
  file: UploadFileInfo
  fileList: UploadFileInfo[]
  event?: Event | undefined
}) {
  const { file, status } = fileInfo.file
  if (status === "removed") {
    fileRef.value = null
    model.value.logo = undefined

    return
  }

  fileRef.value = file || null

  if (!logoUploadRef.value) {
    return
  }
  const { uploadRef } = logoUploadRef.value
  void nextTick(() => {
    uploadRef.submit()
  })
}

function handleUploadedLogo(fileInfo: Api.Attachment.AttachmentItem) {
  const { id } = fileInfo
  model.value.logo = id
}

watch(
  () => isShown.value,
  (shown) => {
    if (shown) {
      emits("modal:open")
      void nextTick(() => {
        restoreModel()
      })
    }
    else {
      emits("modal:close")
    }
  },
)
</script>

<style scoped lang="sass">
:deep(.n-base-selection-tags)
  justify-content: flex-start!important
  align-items: start!important
  flex-direction: column!important
</style>

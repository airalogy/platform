<template>
  <div>
    <n-button
      :ghost="props.buttonType === 'ghost'"
      :text="props.buttonType === 'text'"
      v-bind="props.buttonProps"
      @click.stop="showModal"
    >
      <template v-if="props.showIcon" #icon>
        <add-circle-outline />
      </template>
      {{ triggerText }}
    </n-button>
    <n-modal
      :show="isShown"
      preset="card"
      size="huge"
      class="w-70vw"
      header-class="border-b !py-5 !px-6"
      content-class="!px-6 !py-6"
      :mask-closable="false"
      @update:show="handleModalShow"
    >
      <template #header>
        {{ $t("page.labs.createLabModal.title") }}
      </template>
      <div class="max-h-85vh w-full overflow-x-visible overflow-y-auto">
        <n-form ref="formRef" :model="model" :rules="rules" size="large">
          <n-form-item :label="$t('page.labs.createLabModal.displayNameLabel')" path="displayName">
            <n-tooltip trigger="focus" placement="top-start" class="max-w-70%">
              <template #trigger>
                <n-input
                  v-model:value="model.displayName"
                  type="text"
                  :maxlength="40"
                  show-count
                  required
                  :placeholder="$t('page.labs.createLabModal.displayNamePlaceholder')"
                  @update:value="handleUpdateDisplayName"
                />
              </template>
              {{ $t("page.labs.createLabModal.displayNameTip") }}
            </n-tooltip>
          </n-form-item>
          <n-form-item :label="$t('page.labs.createLabModal.labIdLabel')" path="uid">
            <common-id-input
              v-model="model.uid"
              type="lab"
              :show-prefix="true"
              :check-loading="checkLoading"
              @update:value="handleUpdateUid"
              @check="handleValidateUid"
            />
          </n-form-item>
          <n-form-item :label="$t('common.description')" path="description">
            <n-input
              v-model:value="model.description"
              :maxlength="64"
              show-count
              :placeholder="$t('page.labs.createLabModal.descriptionPlaceholder')"
            />
          </n-form-item>
          <!-- <n-form-item label="Select type" path="type">
            <n-radio-group v-model:value="model.type">
              <n-radio
                v-for="item in labTypeList"
                :key="item.value"
                :value="item.value"
                size="small"
                class="capitalize first:mr-4"
              >
                {{ item.label }}
              </n-radio>
            </n-radio-group>
          </n-form-item> -->
          <n-form-item :label="$t('common.addMembers')" path="members">
            <n-select
              v-model:value="memberIdList"
              :options="memberOptions"
              :render-label="renderLabel"
              :render-tag="renderMultipleSelectTag"
              :loading="loading"
              :clear-filter-after-select="true"
              :placeholder="$t('common.memberSearchPlaceholder')"
              multiple
              remote
              clearable
              filterable
              :show="isShowMenu"
              @search="handleSearch"
              @clear="handleClear"
              @update:value="handleValueChange"
            />
          </n-form-item>
          <n-form-item :label="$t('page.labs.createLabModal.logoLabel')" path="logo">
            <form-upload-file
              ref="logoUploadRef"
              :upload-props="{ accept: 'image/*' }"
              @update:file="handleSelectLogo"
              @uploaded:file="handleUploadedLogo"
              @finish="handleFinishUpload"
            />
          </n-form-item>
        </n-form>

        <n-alert type="info" class="mb-6">
          <template #header>
            {{ $t("page.labs.createLabModal.defaultProjectsTitle") }}
          </template>
          {{ $t("page.labs.createLabModal.defaultProjectsIntro") }}
          <ul class="ml-4 mt-2 list-disc">
            <li><strong>public_protocols</strong> - {{ $t("page.labs.createLabModal.defaultProjectsPublic") }}</li>
            <li><strong>lab_protocols</strong> - {{ $t("page.labs.createLabModal.defaultProjectsPrivate") }}</li>
          </ul>
        </n-alert>

        <div class="flex items-center justify-end">
          <n-button size="medium" class="mr-4" :disabled="submitting" @click="handleCancel">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button
            size="medium"
            type="primary"
            :disabled="loading"
            :loading="submitting"
            @click="handleConfirm"
          >
            {{ $t("common.confirm") }}
          </n-button>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { ILabValue } from "@/utils/dictionary"
import type {
  SelectOption,
  SelectProps,
  SelectRenderLabel,
  SelectRenderTag,
} from "naive-ui/es/select"
import { createDisplayNameValidator, createUidValidator, useBoolean, useFormRules, useLoading, useNaiveForm, useShowModal } from "@/composables"
import { checkLabUid, postNewLab } from "@/service/api/labs"

import { postNewProject } from "@/service/api/projects"
import { fetchUserList } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { snakeCase } from "@/utils/changeCase"
import { convertDisplayname } from "@/utils/convertDisplayname"

import CommonIdInput from "@airalogy/components/common/common-id-input.vue"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { useDebounceFn } from "@vueuse/core"
import AddCircleOutline from "~icons/ion/add-circle-outline"
import { NAvatar, NSelect, NText, type UploadFileInfo, type UploadInst, useDialog } from "naive-ui"
import { type ButtonProps, NButton } from "naive-ui/es/button"
import LabMemberTag from "../lab-member-tag.vue"

interface IProps {
  buttonType?: "text" | "ghost"
  showIcon?: boolean
  trigger?: string
  buttonProps?: ButtonProps & { class?: string }
}
const props = withDefaults(defineProps<IProps>(), {
  buttonType: "ghost",
  showIcon: true,
  trigger: "",
  buttonProps: () => ({}),
})

const emits = defineEmits<IEmits>()

interface FormModel {
  logo?: string
  uid?: string
  displayName?: string
  description?: string
  type?: ILabValue
}

const { isShown, showModal, hideModal, setModalStatus } = useShowModal()
const triggerText = computed(() => props.trigger || $t("common.newLab"))
const { bool: isShowMenu, setFalse: hideMenu, setTrue: showMenu } = useBoolean()
const { defaultRequiredRule } = useFormRules()
const { formRef, validate } = useNaiveForm()
const { loading, startLoading, endLoading } = useLoading()
const message = useClosableMessage()

const labTypeList: { label: string, value: FormModel["type"] }[] = [
  { label: "private", value: 1 },
  { label: "public", value: 2 },
]

interface IEmits {
  (e: "modal:new-lab", val: Api.Lab.LabInfo): void
  (e: "modal:close"): void
  (e: "modal:open"): void
}

const authStore = useAuthStore()

const rules: Partial<Record<keyof FormModel, App.Global.FormRule[]>> = {
  displayName: createDisplayNameValidator($t("page.labs.createLabModal.displayNameLabel")),
  uid: createUidValidator({
    fieldName: $t("page.labs.createLabModal.labIdLabel"),
    checkDuplicate: checkLabUid,
    payloadKey: "lab",
  }),
}

const memberOptions = ref<SelectOption[]>([])
interface IMember {
  label: string
  value: string
  username: string
  email: string
  role: Api.Lab.LabRole
  alias?: string
}
const selectedMembers = ref<IMember[]>([])

const renderMultipleSelectTag: SelectRenderTag = ({ option, handleClose }) => {
  const { label, value, avatar, username } = option
  return h(LabMemberTag, {
    "name": label as string,
    "username": username as string,
    "id": String(value),
    "avatar": String(avatar),
    "type": "lab",
    "onTag:close": () => {
      handleClose()
    },
    "onTag:select": () => {
      handleClose()
    },
    "onSelect:role": (val: { role: Api.Lab.LabRole, id: string }) => {
      const { role, id } = val
      const target = selectedMembers.value.find(member => member.value === id)

      if (target) {
        target.role = role
      }
    },
    "onUpdate:alias": (val: { alias: string, id: string }) => {
      const { alias, id } = val
      const target = selectedMembers.value.find(member => member.value === id)
      if (target) {
        target.alias = alias
      }
    },
  })
}

const renderLabel: SelectRenderLabel = (option) => {
  return h(
    "div",
    {
      style: {
        display: "flex",
        alignItems: "center",
      },
    },
    [
      h(NAvatar, {
        src: "/images/logo.svg",
        round: true,
        size: "small",
      }),
      h(
        "div",
        {
          style: {
            marginLeft: "12px",
            padding: "4px 0",
          },
        },
        [
          h("div", null, {
            default: () => [
              h("span", null, { default: () => option.label }),
              option.username
                ? h(
                  NText,
                  { depth: 3, tag: "span", style: { marginLeft: "4px" } },
                  { default: () => `(@${option.username as string})` },
                )
                : null,
            ],
          }),
          h(
            NText,
            { depth: 3, tag: "div" },
            {
              default: () => option.email as string,
            },
          ),
        ],
      ),
    ],
  )
}

const memberIdList = ref<number[]>([])

const model = ref<FormModel>({
  uid: undefined,
  description: undefined,
  displayName: undefined,
  type: 1,
})

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

function handleFinishUpload() {
  //
}

function handleUploadedLogo(fileInfo: Api.Attachment.AttachmentItem) {
  const { id } = fileInfo
  model.value.logo = id
}

function handleClearOption() {
  hideMenu()
  setTimeout(() => (memberOptions.value = []), 200)
}

function handleClear() {
  handleClearOption()
  memberIdList.value = []
}

const handleSearch = useDebounceFn(async (val: string) => {
  if (!val) {
    handleClearOption()
    return
  }

  startLoading()
  const { id: userId } = authStore.userInfo
  try {
    const data = await fetchUserList(val)
    showMenu()
    if (data && Array.isArray(data.data)) {
      memberOptions.value = data.data
        .filter(({ id }) => id !== userId)
        .map(
          ({ name, username, id, email }): SelectOption => ({
            label: name || username,
            value: id,
            email,
            role: 3,
          }),
        )
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  finally {
    endLoading()
  }
}, 500)

const handleValueChange: SelectProps["onUpdate:value"] = (
  _,
  option: IMember[],
) => {
  selectedMembers.value = option
  handleClearOption()
}

const shouldUpdateName = ref(true)

async function handleUpdateDisplayName(displayName: string) {
  if (model.value.uid && !shouldUpdateName.value) {
    return
  }
  else if (!model.value.uid) {
    shouldUpdateName.value = true
  }

  const name = await convertDisplayname(displayName)

  model.value.uid = name
}

function handleUpdateUid(val: string) {
  if (shouldUpdateName.value) {
    shouldUpdateName.value = false
  }
}

function restoreModel() {
  model.value = {
    uid: undefined,
    description: undefined,
    displayName: undefined,
    type: 1,
  }

  memberIdList.value = []
  memberOptions.value = []

  formRef.value?.restoreValidation()
}

async function handleModalShow(val: boolean) {
  setModalStatus(val)
  handleClear()
  await nextTick(() => {
    restoreModel()
  })
}

const { loading: submitting, startLoading: startSubmit, endLoading: endSubmit } = useLoading()
const dialog = useDialog()

async function handleCancel() {
  await handleModalShow(false)
}

async function handleConfirm() {
  await validate()

  const { type, uid: rawName, description, displayName, logo } = model.value
  if (!type || !rawName || !displayName) {
    return
  }

  let name = rawName
  const snakeCaseName = snakeCase(name)
  if (snakeCaseName !== name) {
    const isConfirm = await new Promise<boolean>((resolve) => {
      dialog.warning({
        title: $t("common.tip"),
        content: $t("page.labs.createLabModal.snakeCaseWarning", {
          rawUid: rawName,
          snakeCaseUid: snakeCaseName,
        }),
        negativeText: $t("common.cancel"),
        positiveText: $t("common.confirm"),
        onPositiveClick: () => {
          resolve(true)
        },
        onNegativeClick: () => {
          resolve(false)
        },
        onClose: () => {
          resolve(false)
        },
      })
    })

    if (!isConfirm) {
      return
    }
    name = snakeCaseName
  }

  startSubmit()
  try {
    const { data } = await postNewLab({
      name: displayName,
      uid: name,
      description,
      members: selectedMembers.value.map(({ value, role, alias }) => ({ user_id: value, role, alias })),
      logo,
    })

    if (data) {
      // Create default projects
      try {
        const defaultProjects = [
          {
            uid: "public_protocols",
            displayName: "Public Protocols",
            description: "Public protocols repository for sharing protocols with other labs",
            type: 2,
          },
          {
            uid: "lab_protocols",
            displayName: "Lab Protocols",
            description: "Private protocols repository for internal lab sharing",
            type: 1,
          },
        ]

        await Promise.all(
          defaultProjects.map(project =>
            postNewProject({
              labId: data.id,
              uid: project.uid,
              displayName: project.displayName,
              description: project.description,
              type: project.type as 1 | 2,
            }),
          ),
        )

        message.success($t("page.labs.createLabModal.createSuccessWithDefaults", {
          name: model.value.displayName,
        }))
      }
      catch (projectError) {
        message.warning($t("page.labs.createLabModal.defaultProjectsWarning", {
          message: (projectError as Error).message,
        }), { closable: true, duration: 8000 })
      }

      emits("modal:new-lab", data)
      hideModal()
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  finally {
    endSubmit()
  }
}

watch(
  () => isShown.value,
  (shown) => {
    if (shown) {
      emits("modal:open")
    }
    else {
      emits("modal:close")
    }

    void nextTick(() => {
      restoreModel()
    })
  },
)

const {
  loading: checkLoading,
  startLoading: startCheckLoading,
  endLoading: endCheckLoading,
} = useLoading()

async function handleValidateUid() {
  if (!model.value.uid)
    return

  startCheckLoading()
  try {
    await validate(
      (errors) => {
        if (!errors) {
          message.success($t("page.labs.createLabModal.labIdAvailable"))
        }
      },
      rule => rule?.key === "check:duplicate",
    )
  }
  finally {
    endCheckLoading()
  }
}
</script>

<style scoped lang="sass">
:deep(.n-base-selection-tags)
  justify-content: flex-start!important
  align-items: start!important
  flex-direction: column!important
</style>

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
      {{ props.trigger }}
    </n-button>
    <n-modal
      :show="isShown"
      preset="card"
      size="huge"
      class="w-70vw"
      header-class="border-b !py-5 !px-6"
      content-class="!px-0 !py-6 overflow-visible"
      :mask-closable="false"
      @update:show="handleModalShow"
    >
      <template #header>
        {{ $t("page.group.createGroupTitle") }}
      </template>
      <div class="max-h-85vh w-full overflow-x-visible overflow-y-auto px-6">
        <n-form ref="formRef" :model="model" :rules="rules" size="large">
          <!-- <n-form-item label="Upload logo" path="logo">
            <form-upload-file />
          </n-form-item> -->
          <n-form-item :label="$t('page.group.createGroupModal.displayNameLabel')" path="displayName">
            <n-tooltip trigger="focus" placement="top-start" class="max-w-70%">
              <template #trigger>
                <n-input
                  v-model:value="model.displayName"
                  type="text"
                  :maxlength="40"
                  show-count
                  required
                  :placeholder="$t('page.group.createGroupModal.displayNamePlaceholder')"
                  @update:value="handleUpdateDisplayName"
                />
              </template>
              {{ $t("page.group.createGroupModal.displayNameTip") }}
            </n-tooltip>
          </n-form-item>
          <n-form-item :label="$t('page.group.createGroupModal.groupIdLabel')" path="name">
            <common-id-input
              v-model="model.name"
              type="group"
              :lab-uid="props.labInfo?.uid"
              :show-prefix="true"
              :check-loading="checkLoading"
              @update:value="handleUpdateName"
              @check="handleValidateName"
            />
          </n-form-item>
          <n-form-item :label="$t('common.description')" path="description">
            <n-input
              v-model:value="model.description"
              type="textarea"
              :maxlength="64"
              :autosize="true"
              :max-rows="10"
              show-count
              :placeholder="$t('page.group.createGroupModal.descriptionPlaceholder')"
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
          <n-form-item :label="$t('page.group.createGroupModal.selectProjectsLabel')" path="projectIdList">
            <n-select
              v-model:value="model.projectIdList"
              :options="projectOptionList"
              :placeholder="$t('page.group.createGroupModal.selectProjectsPlaceholder')"
              :render-tag="renderProjectTag"
              required
              remote
              multiple
              :loading="loadingState.projects"
              @update:value="handleProjectValueChange"
            />
          </n-form-item>
          <n-form-item :label="$t('common.addMembers')" path="members">
            <n-select
              v-model:value="memberIdList"
              :options="memberOptions"
              :render-label="renderMemberLabel"
              :render-tag="renderMemberTag"
              :loading="loadingState.members"
              :clear-filter-after-select="true"
              :placeholder="$t('common.memberSearchPlaceholder')"
              remote
              multiple
              clearable
              filterable
              :show="isShowMenu"
              @search="handleSearchMember"
              @clear="handleClearMember"
              @update:value="handleMemberValueChange"
            />
          </n-form-item>
        </n-form>
        <div class="flex items-center justify-end">
          <n-button size="medium" class="mr-4" :disabled="loadingKeys.length !== 0" @click="handleCancel">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button
            size="medium"
            type="primary"
            :disabled="loadingKeys.length !== 0"
            :loading="loadingState.submit"
            @click="handleSubmit"
          >
            {{ $t("common.confirm") }}
          </n-button>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { ProjectType } from "@/enum"
import type {
  SelectOption,
  SelectProps,
  SelectRenderLabel,
  SelectRenderTag,
} from "naive-ui/es/select"
import { createDisplayNameValidator, createUidValidator, useBoolean, useFormRules, useLoading, useNaiveForm, useShowModal } from "@/composables"
import { LabRole, ProjectRole } from "@/enum"

import { postNewGroup } from "@/service/api/groups"
import { fetchLabMemberList } from "@/service/api/labs"

import { fetchProjectList } from "@/service/api/projects"

import { fetchUserList } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"

import { snakeCase } from "@/utils/changeCase"
import { convertDisplayname } from "@/utils/convertDisplayname"
import CommonIdInput from "@airalogy/components/common/common-id-input.vue"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { useDebounceFn } from "@vueuse/core"
import AddCircleOutline from "~icons/ion/add-circle-outline"
import MiniSearch from "minisearch"
import { NAvatar, NSelect, NText, useDialog } from "naive-ui"
import { type ButtonProps, NButton } from "naive-ui/es/button"
import { useOrProvideLabInfoStore } from "../../hooks/useLabsInfoStore"
import LabMemberTag from "../lab-member-tag.vue"
import GroupProjectTag, { type IProps as GroupProjectTagProps } from "./group-project-tag.vue"

interface IProps {
  buttonType?: "text" | "ghost"
  showIcon?: boolean
  trigger?: string
  buttonProps?: ButtonProps & { class?: string }
  labInfo?: Api.Lab.LabInfo | null
  projectList?: Api.Project.MyProjectInfo[]
}
const props = withDefaults(defineProps<IProps>(), {
  buttonType: "ghost",
  showIcon: true,
  trigger: $t("common.newGroup"),
  buttonProps: () => ({}),
  labInfo: null,
})

const emits = defineEmits<IEmits>()

interface FormModel {
  name?: string
  displayName?: string
  description?: string
  projectIdList: number[]
}

const { isShown, showModal, hideModal, setModalStatus } = useShowModal()
const { bool: isShowMenu, setFalse: hideMenu, setTrue: showMenu } = useBoolean()
const { defaultRequiredRule } = useFormRules()
const { formRef, validate } = useNaiveForm()
const { loadingState, loadingKeys, startTargetLoading, endTargetLoading } = useLoading(false, ["projects", "members", "submit"])
const message = useClosableMessage()

const { labInfo } = useOrProvideLabInfoStore(null)
// const labTypeList: { label: string; value: FormModel["type"] }[] = [
//   { label: "private", value: 1 },
//   { label: "public", value: 2 },
// ]

interface IEmits {
  (e: "modal:new-group", val: Api.Groups.MyGroupsInfo): void
  (e: "modal:close"): void
  (e: "modal:open"): void
}

const authStore = useAuthStore()

const rules: Partial<Record<keyof FormModel, App.Global.FormRule[]>> = {
  displayName: createDisplayNameValidator($t("page.group.createGroupModal.displayNameLabel")),
  // name: [
  //   defaultRequiredRule,
  //   {
  //     min: 1,
  //     max: 40,
  //     message: "Group name must be between 1 and 40 characters long",
  //     trigger: ["change", "blur"],
  //   },
  //   {
  //     pattern: /^[\w-]*$/,
  //     message: "Group name can only contain letters (a-z, A-Z), numbers (0-9), or hyphens (_-)",
  //     trigger: ["change", "blur"],
  //   },
  //   {
  //     validator: (rule, value, callback) => {
  //       if (/^[_-]|[_-]$/.test(value)) {
  //         return new Error("Group name should not start or end with a hyphen")
  //       }
  //       if (/[_-]{2,}/.test(value)) {
  //         return new Error("Hyphens cannot appear consecutively")
  //       }
  //       return true
  //     },
  //     trigger: ["change", "blur"],
  //   },
  // ],
  name: createUidValidator({ fieldName: $t("page.group.createGroupModal.groupIdLabel") }),
}
// const roleRef = ref<ProjectRole>(ProjectRole.VIEWER)

const memberOptions = ref<SelectOption[]>([])
const selectedMembers = ref<
  { label: string, value: number, username: string, email: string, role: Api.Lab.LabRole }[]
>([])

const selectedProjects = ref<{ project_id: string, role: ProjectRole }[]>([])

const renderProjectTag: SelectRenderTag = ({ option, handleClose }) => {
  const { label, type, value, role } = option as SelectOption & { role: ProjectRole }

  return h(GroupProjectTag, {
    "name": label as string,
    "id": String(value),
    "type": type as ProjectType,
    "topRole": role,
    "role": role,
    "onTag:close": () => {
      handleClose()
    },
    "onTag:select": () => {
      handleClose()
    },
    "onSelect:role": (payload: { role: Api.Project.ProjectRole, id: string }) => {
      const { role, id } = payload

      const target = selectedProjects.value.find(({ project_id }) => project_id === id)

      if (target) {
        target.role = role
      }
    },
  } as GroupProjectTagProps)
}

const handleProjectValueChange: SelectProps["onUpdate:value"] = (
  _,
  option: {
    label: string
    value: string
    role: ProjectRole
  }[],
) => {
  selectedProjects.value = option.map(({ value, role }) => ({ project_id: value, role }))
}

const renderMemberTag: SelectRenderTag = ({ option, handleClose }) => {
  const { label, value, avatar, username } = option
  return h(LabMemberTag, {
    "name": label as string,
    "username": username as string,
    "id": String(value),
    "avatar": String(avatar),
    "role": LabRole.MEMBER,
    "changeRole": false,
    "type": "group",
    "onTag:close": () => {
      handleClose()
    },
    "onTag:select": () => {
      handleClose()
    },
  })
}

const renderMemberLabel: SelectRenderLabel = (option) => {
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
        src: (option.avatar as string) || "/images/avatar_default.svg",
        round: true,
        size: "small",
        objectFit: "cover",
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

const memberIdList = ref<string[]>([])

const model = ref<FormModel>({
  name: undefined,
  description: undefined,
  displayName: undefined,
  projectIdList: [],
})

function handleClearOption() {
  hideMenu()
  setTimeout(() => (memberOptions.value = []), 200)
}

function handleClearMember() {
  handleClearOption()
  memberIdList.value = []
}
const userSearch = new MiniSearch<Api.Lab.MemberListItem>({
  fields: ["name", "email", "username"], // fields to index for full-text search
  storeFields: ["name", "email", "username", "id"], // fields to return with search results
  searchOptions: {
    boost: { name: 2, isoCode: 1.5, dialCode: 1 }, // boost name matches
    fuzzy: 0.2, // enable fuzzy matching
    prefix: true, // enable prefix matching
  },
})

const handleSearchMember = useDebounceFn(async (val: string) => {
  if (!val) {
    handleClearOption()
    return
  }

  startTargetLoading("members")
  const { id: userId } = authStore.userInfo
  const labId = labInfo.value?.id

  try {
    if (labId) {
      const res = await fetchLabMemberList(labId, { page: 1, pageSize: 9999 })
      if (res?.users) {
        userSearch.removeAll()
        userSearch.addAll(res.users)
        const result = userSearch.search(val)
        memberOptions.value = result
          .filter(({ id }) => id !== userId)
          .map(
            ({ name, username, id, email, avatar_url }): SelectOption => ({
              label: name || username,
              username,
              value: id,
              email,
              role: ProjectRole.RECORDER,
              avatar: avatar_url,
            }),
          )
      }
    }
    else {
      const data = await fetchUserList(val)
      if (data && Array.isArray(data.data)) {
        memberOptions.value = data.data
          .filter(({ id }) => id !== userId)
          .map(
            ({ name, username, id, email, avatar_url }): SelectOption => ({
              label: name || username,
              username,
              value: id,
              email,
              role: ProjectRole.RECORDER,
              avatar: avatar_url,
            }),
          )
      }
    }
    showMenu()
  }
  catch (e) {
    message.error((e as Error).message)
  }
  finally {
    endTargetLoading("members")
  }
}, 500)

const handleMemberValueChange: SelectProps["onUpdate:value"] = (
  _,
  option: {
    label: string
    value: number
    username: string
    email: string
    role: Api.Lab.LabRole
  }[],
) => {
  selectedMembers.value = option
  handleClearOption()
}

const shouldUpdateName = ref(true)

async function handleUpdateDisplayName(displayName: string) {
  if (model.value.name && !shouldUpdateName.value) {
    return
  }
  else if (!model.value.name) {
    shouldUpdateName.value = true
  }

  const name = await convertDisplayname(displayName)

  model.value.name = name
}

function handleUpdateName(val: string) {
  if (shouldUpdateName.value) {
    shouldUpdateName.value = false
  }
}

const projectList = inject<Ref<Api.Project.MyProjectInfo[]>>("lab-project-list", ref([]))

type ProjectOption = SelectOption & { role: ProjectRole, type: ProjectType }
const projectOptionList = computed((): ProjectOption[] => {
  return projectList.value.map(
    ({ name, uid, id, type }): ProjectOption => ({
      label: name || uid,
      type,
      role: ProjectRole.RECORDER,
      value: id,
    }),
  )
})

function restoreModel() {
  model.value = {
    name: undefined,
    description: undefined,
    displayName: undefined,
    projectIdList: [],
  }

  memberIdList.value = []
  memberOptions.value = []

  formRef.value?.restoreValidation()
}

async function handleModalShow(val: boolean) {
  setModalStatus(val)
  handleClearMember()
  await nextTick(() => {
    restoreModel()
  })
}

const dialog = useDialog()

async function handleCancel() {
  await handleModalShow(false)
}

async function handleSubmit() {
  await validate()

  const labId = props.labInfo?.id
  if (!labId) {
    message.error($t("page.group.createGroupModal.labNotFound"))
    return
  }

  const { name: rawName, description, displayName, projectIdList } = model.value
  if (!rawName || !displayName) {
    return
  }

  let name = rawName
  const snakeCaseName = snakeCase(name)
  if (snakeCaseName !== name) {
    const isConfirm = await new Promise<boolean>((resolve) => {
      dialog.warning({
        title: $t("common.tip"),
        content: $t("page.group.createGroupModal.snakeCaseWarning", { rawName, snakeCaseName }),
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

  startTargetLoading("submit")
  try {
    const { data } = await postNewGroup({
      name: displayName,
      uid: name,
      description,
      labId,
      memberIdList: memberIdList.value,
      projectList: selectedProjects.value,
    })

    if (data) {
      emits("modal:new-group", data)

      message.success($t("page.group.createGroupModal.createSuccess", { name: model.value.displayName }))
      hideModal()
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  finally {
    endTargetLoading("submit")
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

// async function handleFetchProjects(labId: string, list?: Api.Project.MyProjectInfo[]) {
//   const result = list || await fetchProjectList(labId, { page: 1, pageSize: 999 }).then(data => data?.projects)
//   if (result) {
//     projectOptionList.value = result.map(
//       ({ name, uid, id, type }): SelectOption => ({
//         label: name || uid,
//         type,
//         role: 2,
//         value: id,
//       }),
//     )
//   }
// }

// onMounted(async () => {
//   if (!props.labInfo) {
//     return
//   }

//   await handleFetchProjects(props.labInfo.id)
// })

watch(
  [() => props.labInfo?.id, isShown],
  async ([id, shown]) => {
    if (!id || !shown) {
      return
    }

    const res = await fetchProjectList({ labId: id, page: 1, pageSize: 999 })
    if (res?.projects) {
      projectList.value = res.projects
    }
  },
  { immediate: true },
)

const {
  loading: checkLoading,
  startLoading: startCheckLoading,
  endLoading: endCheckLoading,
} = useLoading()

async function handleValidateName() {
  if (!model.value.name)
    return

  startCheckLoading()
  try {
    await validate(
      (errors) => {
        if (!errors) {
          message.success($t("page.group.createGroupModal.groupIdAvailable"))
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
</style>

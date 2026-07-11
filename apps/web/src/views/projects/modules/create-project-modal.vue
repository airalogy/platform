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
      :class="instanceStore.isSingleLab ? 'max-w-[calc(100vw-32px)] w-180' : 'w-70vw'"
      header-class="border-b !py-5 !px-6"
      content-class="!px-6 !py-6"
      :mask-closable="false"
      @update:show="setModalStatus"
    >
      <template #header>
        {{ $t("page.project.createProjectModal.title") }}
      </template>
      <n-form ref="formRef" :model="model" :rules="rules" size="large" label-placement="top">
        <n-form-item :label="$t('page.project.createProjectModal.labLabel')" path="labId">
          <n-select
            v-model:value="model.labId"
            :options="options"
            :loading="loadingState.labs"
            required
            remote
            clearable
            placement="top"
            :disabled="!props.showSelect"
            @update-show="fetchLabs"
          >
            <template v-if="labList.length > 0 && !instanceStore.isSingleLab" #action>
              <create-lab-modal
                show-icon
                :button-props="{ size: 'small' }"
                @modal:new-lab="handleAddLab"
              />
            </template>
          </n-select>
        </n-form-item>
        <n-form-item :label="$t('page.project.createProjectModal.parentProjectLabel')" path="parentProjectId">
          <div class="w-full">
            <n-select
              v-model:value="model.parentProjectId"
              :options="parentProjectOptions"
              :loading="loadingState.parentProjects"
              clearable
              filterable
              :disabled="!selectedLabUid || isParentProjectFixed"
              :placeholder="$t('page.project.createProjectModal.parentProjectPlaceholder')"
            />
            <div class="mt-2 text-sm text-gray-500">
              {{ isParentProjectFixed ? $t("page.project.createProjectModal.parentProjectFixedHint") : $t("page.project.createProjectModal.parentProjectHint") }}
            </div>
          </div>
        </n-form-item>
        <n-form-item :label="$t('page.project.createProjectModal.displayNameLabel')" path="displayName">
          <n-tooltip trigger="focus" placement="top-start" class="max-w-70%">
            <template #trigger>
              <n-input
                v-model:value="model.displayName"
                type="text"
                :maxlength="30"
                show-count
                required
                :placeholder="$t('page.project.createProjectModal.displayNamePlaceholder')"
                @update:value="handleUpdateDisplayName"
              />
            </template>
            {{ $t("page.project.createProjectModal.displayNameTip") }}
          </n-tooltip>
        </n-form-item>
        <n-form-item :label="$t('page.project.createProjectModal.projectIdLabel')" path="uid">
          <common-id-input
            v-model="model.uid"
            type="project"
            :lab-uid="selectedLabUid"
            :show-prefix="true"
            :check-loading="checkLoading"
            :disabled="!selectedLabUid"
            @update:value="handleUpdateName"
            @check="handleValidateUid"
          />
        </n-form-item>
        <n-form-item :label="$t('common.description')" path="description">
          <n-input
            v-model:value="model.description"
            :maxlength="64"
            show-count
            :placeholder="$t('page.project.createProjectModal.descriptionPlaceholder')"
          />
        </n-form-item>

        <n-form-item :label="$t('page.project.createProjectModal.withDiaryLabel')" label-placement="top" :show-feedback="false">
          <div class="w-full">
            <n-checkbox v-model:checked="model.withDiary">
              {{ $t("page.project.createProjectModal.withDiaryOption") }}
            </n-checkbox>
            <div class="mt-2 text-sm text-gray-500">
              {{ $t("page.project.createProjectModal.withDiaryHint") }}
            </div>
          </div>
        </n-form-item>

        <n-form-item v-if="!instanceStore.isSingleLab" :label="$t('page.project.settingsPage.visibilityLabel')" path="type" label-placement="left" required :show-feedback="false">
          <n-radio-group v-model:value="model.type">
            <n-radio
              v-for="item in labTypeList"
              :key="item.value"
              :value="item.value"
              size="small"
              class="capitalize first:mr-4"
              :disabled="Boolean(model.parentProjectId)"
            >
              {{ item.label }}
            </n-radio>
          </n-radio-group>
          <div v-if="model.parentProjectId" class="mt-2 text-sm text-gray-500">
            {{ $t("page.project.createProjectModal.subprojectVisibilityHint") }}
          </div>
        </n-form-item>

        <n-form-item v-if="model.parentProjectId" :label="$t('page.project.createProjectModal.accessSetupLabel')" label-placement="top" :show-feedback="false">
          <div class="w-full">
            <n-checkbox v-model:checked="model.copyMembers">
              {{ $t("page.project.createProjectModal.copyMembersOption") }}
            </n-checkbox>
            <div class="mt-2 text-sm text-gray-500">
              {{ $t("page.project.createProjectModal.copyMembersHint") }}
            </div>
          </div>
        </n-form-item>
      </n-form>
      <div class="flex items-center justify-end">
        <n-button size="medium" class="mr-4" :disabled="loadingState.submit" @click="handleCancel">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button
          size="medium"
          type="primary"
          :disabled="loadingKeys.length !== 0"
          :loading="loadingState.submit"
          @click="handleConfirm"
        >
          {{ $t("common.confirm") }}
        </n-button>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { SelectOption } from "naive-ui/es/select"
import { createDisplayNameValidator, useBoolean, useFormRules, useLoading, useNaiveForm, useShowModal } from "@/composables"
import { createUidValidator } from "@/composables/useForm"
import { diaryProtocol } from "@/constants/protocol"
import { postUploadProtocol } from "@/service/api/project-protocols"
import { checkProjectUid, fetchProjectList, postNewProject } from "@/service/api/projects"
import { fetchUserLabs } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { snakeCase } from "@/utils/changeCase"
import { convertDisplayname } from "@/utils/convertDisplayname"
import { convertProtocolToZip } from "@/utils/protocolPackage"
import CreateLabModal from "@/views/labs/modules/lab/create-lab-modal.vue"
import CommonIdInput from "@airalogy/components/common/common-id-input.vue"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import AddCircleOutline from "~icons/ion/add-circle-outline"
import { useDialog } from "naive-ui"
import { type ButtonProps, NButton } from "naive-ui/es/button"

const props = withDefaults(defineProps<IProps>(), {
  buttonType: "ghost",
  showIcon: true,
  trigger: "",
  buttonProps: () => ({}),
  showSelect: true,
  labInfo: null,
  parentProject: null,
})

const emits = defineEmits<IEmits>()

const { isShown, showModal, hideModal, setModalStatus } = useShowModal()
const triggerText = computed(() => props.trigger || $t("common.newProject"))

interface IProps {
  buttonType?: "text" | "ghost"
  showIcon?: boolean
  buttonProps?: ButtonProps & { class?: string }
  trigger?: string
  showSelect?: boolean
  labInfo?: Api.Lab.LabInfo | null
  parentProject?: Api.Project.MyProjectInfo | null
}

interface FormModel {
  uid: string | null
  displayName: string | null
  description: string | null
  labId: string | null
  parentProjectId: string | null
  type: 1 | 2
  copyMembers: boolean
  withDiary: boolean
}

interface IEmits {
  (e: "modal:new-project", val: Api.Project.MyProjectInfo): void
  (e: "modal:close"): void
  (e: "modal:open"): void
}

const { defaultRequiredRule } = useFormRules()
const { formRef, validate } = useNaiveForm()
const message = useClosableMessage()
const instanceStore = useInstanceStore()

const { loadingState, loadingKeys, startTargetLoading, endTargetLoading } = useLoading(false, ["labs", "submit", "parentProjects"])
const labList = ref<Api.Lab.LabInfo[]>([])
const parentProjectList = ref<Api.Project.MyProjectInfo[]>([])

const model = ref<FormModel>({
  uid: null,
  description: null,
  displayName: null,
  labId: props.labInfo?.id ?? null,
  parentProjectId: props.parentProject?.id ?? null,
  type: 1,
  copyMembers: true,
  withDiary: false,
})

const selectedLabUid = computed(() => {
  const selectedLab = labList.value.find(lab => lab.id === model.value.labId)
  return selectedLab?.uid || props.labInfo?.uid || ""
})

const isParentProjectFixed = computed(() => Boolean(props.parentProject?.id))
const parentProjectOptions = computed((): SelectOption[] => {
  return parentProjectList.value.map(project => ({
    label: `${project.name} (${project.uid})`,
    value: project.id,
  }))
})
const selectedParentProject = computed(() => {
  return parentProjectList.value.find(project => project.id === model.value.parentProjectId) || props.parentProject || null
})

const {
  loading: checkLoading,
  startLoading: startCheckLoading,
  endLoading: endCheckLoading,
} = useLoading()

const dialog = useDialog()

const rules: Partial<Record<keyof FormModel, App.Global.FormRule[]>> = {
  displayName: createDisplayNameValidator($t("page.project.createProjectModal.displayNameLabel")),
  uid: createUidValidator({ fieldName: $t("page.project.createProjectModal.projectIdLabel"), checkDuplicate: checkProjectUid, duplicateCheckArgs: () => ({ labUid: selectedLabUid.value }), payloadKey: "uid" }),
  labId: [defaultRequiredRule],
}

const labTypeList: { label: string, value: FormModel["type"] }[] = [
  { label: $t("page.project.settingsPage.visibility.privateLabel"), value: 1 },
  { label: $t("page.project.settingsPage.visibility.publicLabel"), value: 2 },
]

const options = computed((): SelectOption[] => {
  const list = labList.value

  if (list.length > 0) {
    return list.map((it) => {
      const { name, uid, id } = it

      return {
        label: `${name}  (${uid})`,
        value: id,
        disabled: false,
      }
    })
  }
  else if (props.labInfo) {
    const { name, uid, id } = props.labInfo

    return [
      {
        label: `${name}  (${uid})`,
        value: id,
        disabled: false,
      },
    ]
  }

  if (instanceStore.isSingleLab) {
    return [{
      label: $t("page.project.createProjectModal.labEmptyLabel"),
      value: -1,
      disabled: true,
    }]
  }

  return [
    {
      label: $t("page.project.createProjectModal.labEmptyLabel"),
      value: -1,
      disabled: true,
      render: ({ node, option, selected }) => {
        return h("div", { class: "p-4 flex items-center justify-between text-3.5 text-gray" }, [
          h("span", null, { default: () => option.label }),
          h(CreateLabModal, {
            "showIcon": false,
            "trigger": $t("page.project.createProjectModal.labEmptyAction"),
            "buttonProps": { size: "small" },
            "onModal:new-lab": handleAddLab,
          }),
        ])
      },
    },
  ]
})

watch(
  () => props.labInfo?.id,
  (id) => {
    if (id) {
      model.value.labId = id
    }
  },
  { immediate: true },
)

watch(
  () => props.parentProject,
  (project) => {
    if (!project) {
      return
    }
    model.value.parentProjectId = project.id
    model.value.labId = project.lab_id
    model.value.type = project.type
    parentProjectList.value = [project]
  },
  { immediate: true },
)

watch(
  () => selectedParentProject.value,
  (project) => {
    if (project) {
      model.value.type = project.type
    }
  },
  { immediate: true },
)

const currentOrigin = computed(() => {
  return `${window.location.origin}/project/`
})

function handleAddLab(info: Api.Lab.LabInfo) {
  const { id, name } = info
  model.value.labId = id
  message.success($t("page.project.createProjectModal.labCreateSuccess", { name }))
  labList.value.push(info)
}

function handleCancel() {
  hideModal()
}

async function loadParentProjects() {
  if (!model.value.labId) {
    parentProjectList.value = props.parentProject ? [props.parentProject] : []
    return
  }
  if (props.parentProject) {
    parentProjectList.value = [props.parentProject]
    return
  }

  startTargetLoading("parentProjects")
  try {
    const data = await fetchProjectList({
      labId: model.value.labId,
      rootOnly: true,
      page: 1,
      pageSize: 999,
    })
    parentProjectList.value = (data?.projects || []).filter(project => !project.parent_project_id)
  }
  catch (e) {
    message.error((e as Error).message)
  }
  finally {
    endTargetLoading("parentProjects")
  }
}

async function handleConfirm() {
  await validate()

  const { uid: rawUid, displayName, labId, description, parentProjectId, copyMembers, type, withDiary } = model.value
  if (!labId) {
    message.error($t("page.project.createProjectModal.labRequired"))
    return
  }
  if (!rawUid) {
    message.error($t("page.project.createProjectModal.projectIdRequired"))
    return
  }
  if (!displayName) {
    message.error($t("page.project.createProjectModal.displayNameRequired"))
    return
  }

  const snakeCaseUid = snakeCase(rawUid)
  if (snakeCaseUid !== rawUid) {
    const isConfirm = await new Promise<boolean>((resolve) => {
      dialog.warning({
        title: $t("common.tip"),
        content: $t("page.project.createProjectModal.snakeCaseWarning", { rawUid, snakeCaseUid }),
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
    model.value.uid = snakeCaseUid
  }

  startTargetLoading("submit")
  try {
    const { data } = await postNewProject({
      labId,
      parentProjectId: parentProjectId || undefined,
      copyMembers: parentProjectId ? copyMembers : undefined,
      uid: rawUid,
      displayName,
      description: description || undefined,
      type,
    })
    if (!data) {
      return
    }
    const { id } = data
    if (withDiary) {
      try {
        const msgInstance = message.loading($t("page.project.createProjectModal.creatingWithDiary"), { duration: 0 })
        if (!diaryProtocol) {
          throw new Error("Failed to create diary unit")
        }

        const diaryPackage = await convertProtocolToZip(diaryProtocol, "diary")

        await postUploadProtocol({
          projectId: id,
          file: diaryPackage,
        })

        msgInstance.destroy()
      }
      catch (diaryError) {
        message.warning($t("page.project.createProjectModal.diaryCreateFailed"), { closable: true, duration: 5000 })
      }
    }

    emits("modal:new-project", data)
    const successKey = withDiary
      ? "page.project.createProjectModal.createSuccessWithDiary"
      : "page.project.createProjectModal.createSuccess"
    message.success($t(successKey, { name: displayName }))
    hideModal()
  }
  catch (e) {
    message.error((e as Error).message)
  }
  finally {
    endTargetLoading("submit")
  }
}

const { bool: syncUid, setTrue: startSyncUid, setFalse: endSyncUid } = useBoolean(true)

async function handleUpdateDisplayName(displayName: string) {
  if (!syncUid.value) {
    return
  }

  const uid = await convertDisplayname(displayName)

  model.value.uid = uid
}

const authStore = useAuthStore()
async function fetchLabs(show: boolean) {
  if (!show) {
    return
  }

  try {
    const data = await fetchUserLabs(authStore.userInfo.id)
    if (data) {
      labList.value = data.labs
      if (instanceStore.isSingleLab && !props.labInfo) {
        const configuredLab = data.labs.find(lab => lab.uid === instanceStore.lab?.uid)
        model.value.labId = configuredLab?.id ?? null
      }
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
}

watch(
  () => isShown.value,
  async (shown) => {
    if (shown) {
      emits("modal:open")
      if (instanceStore.isSingleLab) {
        await fetchLabs(true)
      }
      await loadParentProjects()
    }
    else {
      emits("modal:close")
    }
  },
)

watch(
  () => model.value.labId,
  async (labId, prevLabId) => {
    if (!labId || !isShown.value) {
      return
    }
    if (!isParentProjectFixed.value && prevLabId && prevLabId !== labId) {
      model.value.parentProjectId = null
    }
    await loadParentProjects()
  },
)

async function handleValidateUid() {
  if (!model.value.uid)
    return

  startCheckLoading()
  try {
    await validate(
      (errors) => {
        if (!errors) {
          message.success($t("page.project.createProjectModal.projectIdAvailable"))
        }
      },
      (rule) => {
        return Boolean(rule?.required || rule?.key?.startsWith("check:"))
      },
    )
  }
  finally {
    endCheckLoading()
  }
}

function handleUpdateName(val: string) {
  if (val) {
    endSyncUid()
  }
  else {
    startSyncUid()
  }
}
</script>

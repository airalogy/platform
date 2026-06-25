<template>
  <div class="size-full">
    <n-form
      v-if="projectInfo"
      ref="formRef"
      :model="model"
      :rules="rules"
      size="large"
      label-width="auto"
      class="size-full flex-1 px-10"
    >
      <!-- General Settings -->
      <settings-card
        :title="$t('page.project.settingsPage.generalTitle')"
        :description="$t('page.project.settingsPage.generalDescription')"
      >
        <!-- Logo Upload Section -->
        <n-form-item :label="$t('page.project.settingsPage.logoLabel')" path="logo">
          <div class="flex flex-col space-y-2">
            <form-upload-file
              ref="logoUploadRef"
              :default-file-list="defaultFileList"
              :upload-props="{ accept: 'image/*', showRemoveButton: true }"
              @update:file="handleSelectLogo"
              @uploaded:file="handleUploadedLogo"
            />
            <p class="text-xs text-gray-500">
              {{ $t("page.project.settingsPage.logoHint") }}
            </p>
          </div>
        </n-form-item>

        <!-- Project ID Section -->
        <n-form-item :label="$t('page.project.settingsPage.projectIdLabel')">
          <div class="flex flex-col space-y-2">
            <n-input
              :value="projectInfo?.uid || ''"
              type="text"
              disabled
              class="!rounded-lg"
            />
            <p class="text-xs text-gray-500">
              {{ $t("page.project.settingsPage.projectIdHint") }}
            </p>
          </div>
        </n-form-item>

        <!-- Project Name Section -->
        <n-form-item :label="$t('page.project.settingsPage.nameLabel')" path="name">
          <n-input
            v-model:value="model.name"
            type="text"
            :maxlength="40"
            required
            show-count
            :placeholder="$t('page.project.settingsPage.namePlaceholder')"
            class="!rounded-lg"
          />
        </n-form-item>

        <!-- Description Section -->
        <n-form-item :label="$t('page.project.settingsPage.descriptionLabel')" path="description">
          <n-input
            v-model:value="model.description"
            type="textarea"
            :maxlength="128"
            :autosize="{ minRows: 3, maxRows: 6 }"
            show-count
            :placeholder="$t('page.project.settingsPage.descriptionPlaceholder')"
            class="!rounded-lg"
          />
        </n-form-item>

        <template #footer>
          <div class="flex items-center justify-end gap-2">
            <n-button
              size="medium"
              :disabled="submitting"
              @click="handleCancel"
            >
              {{ $t("common.cancel") }}
            </n-button>
            <n-button
              size="medium"
              type="primary"
              :disabled="submitting || !isGeneralDirty"
              :loading="submitting"
              class="!px-6"
              @click="handleConfirm"
            >
              {{ $t("page.project.settingsPage.saveAction") }}
            </n-button>
          </div>
        </template>
      </settings-card>

      <settings-card
        :title="$t('page.project.settingsPage.subprojectsTitle')"
        :description="$t('page.project.settingsPage.subprojectsDescription')"
        class="mt-6"
      >
        <div class="flex flex-col gap-5">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div class="text-sm text-gray-900 font-600">
                {{ $t("page.project.settingsPage.parentProjectTitle") }}
              </div>
              <router-link
                v-if="projectInfo.parent_project_uid"
                :to="{ name: 'project-protocols', params: { labUid: projectInfo.lab_uid, projectUid: projectInfo.parent_project_uid } }"
                class="mt-2 inline-flex text-sm text-primary hover:underline"
              >
                {{ projectInfo.parent_project_name || projectInfo.parent_project_uid }}
              </router-link>
              <div v-else class="mt-2 text-sm text-gray-500">
                {{ $t("page.project.settingsPage.topLevelProjectHint") }}
              </div>
            </div>

            <create-project-modal
              v-if="canCreateSubproject"
              button-type="ghost"
              :trigger="$t('page.project.settingsPage.createSubprojectAction')"
              :show-select="false"
              :show-icon="false"
              :lab-info="subprojectLabInfo"
              :parent-project="projectInfo"
              @modal:new-project="handleCreateSubproject"
            />
          </div>

          <div>
            <div class="text-sm text-gray-900 font-600">
              {{ $t("page.project.settingsPage.childProjectsTitle") }}
            </div>
            <div class="mt-3">
              <n-spin :show="subprojectsLoading">
                <n-empty
                  v-if="!subprojects.length"
                  :description="$t('page.project.settingsPage.childProjectsEmpty')"
                  size="small"
                />
                <div
                  v-else
                  class="overflow-hidden border border-gray-200 rounded-lg"
                >
                  <router-link
                    v-for="item in subprojects"
                    :key="item.id"
                    :to="{ name: 'project-protocols', params: { labUid: item.lab_uid, projectUid: item.uid } }"
                    class="flex items-center justify-between gap-4 border-b border-gray-100 px-4 py-3 text-sm last:border-b-0 hover:bg-gray-50"
                  >
                    <div class="min-w-0">
                      <div class="truncate text-gray-900 font-500">
                        {{ item.name }}
                      </div>
                      <div class="mt-1 text-xs text-gray-500">
                        {{ item.uid }} · {{ item.protocols_count || 0 }} protocols · {{ item.users_count || 0 }} members
                      </div>
                    </div>
                    <span class="text-xs text-gray-400">
                      {{ item.type === ProjectType.PUBLIC ? $t("page.project.settingsPage.visibility.publicLabel") : $t("page.project.settingsPage.visibility.privateLabel") }}
                    </span>
                  </router-link>
                </div>
              </n-spin>
            </div>
          </div>
        </div>
      </settings-card>

      <!-- Danger Zone -->
      <div class="mb-4 mt-6 border-t border-gray-200" />
      <settings-card
        :title="$t('page.project.settingsPage.dangerTitle')"
        :description="$t('page.project.settingsPage.dangerDescription')"
        :is-danger="true"
      >
        <!-- Project Type Section -->
        <n-form-item :show-require-mark="false" :label="$t('page.project.settingsPage.visibilityLabel')" path="type">
          <div class="w-full flex items-start justify-between gap-4 pt-2">
            <div class="min-w-0 flex flex-col gap-2">
              <span
                v-if="visibilityLabel"
                class="w-fit inline-flex items-center whitespace-nowrap rounded px-2 py-0.5 text-xs font-500"
                :class="visibilityClass"
              >
                {{ visibilityLabel }}
              </span>
              <div class="text-sm text-gray-500">
                {{ currentVisibilityDescription }}
              </div>
            </div>
            <n-button
              size="small"
              type="error"
              :disabled="isDefaultProject"
              @click="openVisibilityModal"
            >
              {{ $t("page.project.settingsPage.changeVisibilityAction") }}
            </n-button>
          </div>
          <n-text v-if="isDefaultProject" depth="3" class="mt-2 block text-xs text-red-500">
            {{ $t("page.project.settingsPage.defaultProjectVisibilityHint") }}
          </n-text>
        </n-form-item>

        <n-divider class="!mt-2" />
        <!-- Public Access Role Section -->
        <template v-if="model.type === ProjectType.PUBLIC">
          <n-form-item
            :label="$t('page.project.settingsPage.publicAccessRoleLabel')"
            path="public_access_role"
            class="transition-all duration-300 ease-in-out"
            :show-require-mark="false"
          >
            <div class="w-full flex items-start justify-between gap-4">
              <div class="min-w-0">
                <div class="text-gray-900 font-medium">
                  {{ currentAccessRoleLabel }}
                </div>
                <div class="mt-1 text-sm text-gray-500">
                  {{ currentAccessRoleDescription }}
                </div>
              </div>
              <n-button size="small" type="error" @click="openAccessRoleModal">
                {{ $t("page.project.settingsPage.changeAccessRoleAction") }}
              </n-button>
            </div>
          </n-form-item>
          <n-divider class="!mt-2" />
        </template>

        <div class="flex items-center">
          <div>
            <h4 class="text-4">
              {{ $t("page.project.settingsPage.deleteTitle") }}
            </h4>
            <span class="color-text-secondary">
              {{ $t("page.project.settingsPage.deleteDescription") }}
            </span>
          </div>
          <n-button size="small" type="error" class="ml-auto" :disabled="isDefaultProject" @click="handleDelete">
            {{ $t("common.delete") }}
          </n-button>
        </div>
        <n-text v-if="isDefaultProject" depth="3" class="mt-2 block text-xs text-red-500">
          {{ $t("page.project.settingsPage.defaultProjectDeleteHint") }}
        </n-text>
      </settings-card>
    </n-form>

    <!-- Delete Confirmation Modal -->
    <delete-confirmation-modal
      :show="showDeleteModal"
      :entity-name="$t('page.project.settingsPage.deleteEntityName')"
      :item-name="projectInfo?.name || ''"
      :delete-confirmation-text="deleteConfirmationText"
      :is-delete-confirmation-valid="isDeleteConfirmationValid"
      :deleting="deleting"
      @update:delete-confirmation-text="deleteConfirmationText = $event"
      @confirm="confirmDelete"
      @cancel="cancelDelete"
    />

    <n-modal v-model:show="showVisibilityModal" :mask-closable="false">
      <n-card class="w-[520px]" :bordered="false" role="dialog" aria-modal="true">
        <div class="mb-2 text-5 font-600">
          {{ $t("page.project.settingsPage.changeVisibilityTitle") }}
        </div>
        <div class="mb-4 text-3 text-gray-500">
          {{ $t("page.project.settingsPage.changeVisibilityHint") }}
        </div>
        <n-radio-group v-model:value="visibilityDraft" class="flex flex-col gap-3">
          <n-radio
            v-for="type in typeList"
            :key="type.value"
            :value="type.value"
            class="!items-start"
          >
            <div class="ml-2 flex flex-col">
              <span class="text-gray-900 font-medium">
                {{ type.label }}
              </span>
              <span class="mt-1 text-sm text-gray-500">
                {{ type.description }}
              </span>
            </div>
          </n-radio>
        </n-radio-group>
        <div class="mt-6 flex justify-end gap-2">
          <n-button @click="closeVisibilityModal">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button
            type="primary"
            :disabled="!visibilityDraft || visibilityDraft === model.type"
            :loading="visibilitySubmitting"
            @click="confirmVisibilityDraft"
          >
            {{ $t("common.confirm") }}
          </n-button>
        </div>
      </n-card>
    </n-modal>

    <n-modal v-model:show="showAccessRoleModal" :mask-closable="false">
      <n-card class="w-[520px]" :bordered="false" role="dialog" aria-modal="true">
        <div class="mb-2 text-5 font-600">
          {{ $t("page.project.settingsPage.changeAccessRoleTitle") }}
        </div>
        <div class="mb-4 text-3 text-gray-500">
          {{ $t("page.project.settingsPage.changeAccessRoleHint") }}
        </div>
        <n-radio-group v-model:value="accessRoleDraft" class="flex flex-col gap-3">
          <n-radio
            v-for="role in publicAccessRoleList"
            :key="role.value"
            :value="role.value"
            class="!items-start"
          >
            <div class="ml-2 flex flex-col">
              <span class="text-gray-900 font-medium">
                {{ role.label }}
              </span>
              <span class="mt-1 text-sm text-gray-500">
                {{ role.description }}
              </span>
            </div>
          </n-radio>
        </n-radio-group>
        <div class="mt-6 flex justify-end gap-2">
          <n-button @click="closeAccessRoleModal">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button
            type="primary"
            :disabled="!accessRoleDraft || accessRoleDraft === model.public_access_role"
            :loading="accessRoleSubmitting"
            @click="confirmAccessRoleDraft"
          >
            {{ $t("common.confirm") }}
          </n-button>
        </div>
      </n-card>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { SelectOption } from "naive-ui/es/select"
import { DeleteConfirmationModal, SettingsCard, useLogoUpload } from "@/components/common/settings"
import { useFormRules, useLoading, useNaiveForm } from "@/composables"
import { useProjectVisibility } from "@/composables/useProjectVisibility"
import { getProjectRoleDetailsPublic } from "@/composables/useRoleDescription"
import { useRouterPush } from "@/composables/useRouterPush"
import { ProjectRole, ProjectType } from "@/enum"
import { deleteProject, fetchProjectList, putProjectInfo } from "@/service/api/projects"
import { useProjectInfoStore } from "@/views/project-protocols/hooks/useProjectInfoStore"
import CreateProjectModal from "@/views/projects/modules/create-project-modal.vue"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { isEqual } from "lodash-es"
import { useDialog } from "naive-ui"

const { projectInfo, fetchProjectInfoById } = useProjectInfoStore()!

interface FormModel {
  name?: string
  description?: string
  type?: Api.Lab.GroupType
  logo?: string
  public_access_role?: ProjectRole.RECORDER | ProjectRole.EXPLORER | ProjectRole.VIEWER
}

const { defaultRequiredRule } = useFormRules()
const { formRef, validate } = useNaiveForm()

const rules: Partial<Record<keyof FormModel, App.Global.FormRule[]>> = {
  name: [
    defaultRequiredRule,
    {
      min: 1,
      max: 40,
      message: $t("page.project.settingsPage.validation.nameLength"),
      trigger: ["change", "blur"],
    },
    {
      validator: (rule, value, callback) => {
        if (/^[_\s-]|[_\s-]$/.test(value)) {
          return new Error($t("page.project.settingsPage.validation.nameEdge"))
        }
        if (/[_\s-]{2,}/.test(value)) {
          return new Error($t("page.project.settingsPage.validation.nameRepeat"))
        }
        return true
      },
      trigger: ["change", "blur"],
    },
  ],
  type: [defaultRequiredRule],
  public_access_role: [defaultRequiredRule],
}

const memberOptions = ref<SelectOption[]>([])

const typeList = [
  {
    label: $t("page.project.settingsPage.visibility.publicLabel"),
    value: ProjectType.PUBLIC,
    description: $t("page.project.settingsPage.visibility.publicDescription"),
  },
  {
    label: $t("page.project.settingsPage.visibility.privateLabel"),
    value: ProjectType.PRIVATE,
    description: $t("page.project.settingsPage.visibility.privateDescription"),
  },
]

const defaultProjectUids = new Set(["public_protocols", "lab_protocols"])
const isDefaultProject = computed(() => defaultProjectUids.has(projectInfo.value?.uid || ""))

const projectRoleDetailsPublic = getProjectRoleDetailsPublic()
const publicAccessRoleList = [
  projectRoleDetailsPublic[ProjectRole.VIEWER]!,
  projectRoleDetailsPublic[ProjectRole.EXPLORER]!,
  projectRoleDetailsPublic[ProjectRole.RECORDER]!,
]

const initValue = computed(
  (): FormModel => ({
    name: projectInfo.value?.name,
    description: projectInfo.value?.description,
    type: projectInfo.value?.type,
    logo: projectInfo.value?.logo || undefined,
    public_access_role: projectInfo.value?.public_access_role,
  }),
)

const model = ref<FormModel>({
  name: "",
  description: "",
  type: undefined,
  logo: undefined,
  public_access_role: undefined,
})
const subprojects = ref<Api.Project.MyProjectInfo[]>([])

const isGeneralDirty = computed(() =>
  !isEqual(
    {
      name: model.value.name,
      description: model.value.description,
      logo: model.value.logo,
    },
    {
      name: initValue.value.name,
      description: initValue.value.description,
      logo: initValue.value.logo,
    },
  ),
)
const currentVisibility = computed(() => typeList.find(item => item.value === model.value.type))
const currentVisibilityLabel = computed(() => currentVisibility.value?.label || "")
const currentVisibilityDescription = computed(() => currentVisibility.value?.description || "")
const { visibilityLabel, visibilityClass } = useProjectVisibility(() => model.value.type)
const currentAccessRole = computed(() => publicAccessRoleList.find(role => role.value === model.value.public_access_role))
const currentAccessRoleLabel = computed(() => currentAccessRole.value?.label || "")
const currentAccessRoleDescription = computed(() => currentAccessRole.value?.description || "")
const showVisibilityModal = ref(false)
const visibilityDraft = ref<Api.Lab.GroupType | undefined>(undefined)
const visibilitySubmitting = ref(false)
const showAccessRoleModal = ref(false)
const accessRoleDraft = ref<ProjectRole.RECORDER | ProjectRole.EXPLORER | ProjectRole.VIEWER | undefined>(undefined)
const accessRoleSubmitting = ref(false)
const {
  loading: subprojectsLoading,
  startLoading: startSubprojectsLoading,
  endLoading: endSubprojectsLoading,
} = useLoading()
const subprojectLabInfo = computed(() => {
  if (!projectInfo.value) {
    return null
  }

  return {
    id: projectInfo.value.lab_id,
    uid: projectInfo.value.lab_uid,
    name: projectInfo.value.lab_name,
  } as Api.Lab.LabInfo
})
const canCreateSubproject = computed(() => {
  return Boolean(projectInfo.value?.id) && !projectInfo.value?.parent_project_id && !isDefaultProject.value
})

// Logo upload
const logoUrlValue = computed(() => projectInfo.value?.logo_url || undefined)
const logoRef = computed({
  get: () => model.value.logo,
  set: (value) => { model.value.logo = value },
})
const {
  logoUploadRef,
  defaultFileList,
  handleSelectLogo,
  handleUploadedLogo,
} = useLogoUpload(logoRef, logoUrlValue)

// const defaultFileList = computed(() => {
//   if (!projectInfo.value) {
//     return []
//   }
//   const { logo, logo_url } = projectInfo.value

//   if (logo && logo_url) {
//     return [{
//       id: logo,
//       name: logo,
//       url: logo_url,
//       status: "finished",
//     } as UploadFileInfo]
//   }

//   return []
// })

function restoreModel() {
  model.value = { ...initValue.value }
  memberOptions.value = []
  formRef.value?.restoreValidation()
}

const { loading: submitting, startLoading: startSubmit, endLoading: endSubmit } = useLoading()

const dialog = useDialog()
const message = useClosableMessage()

function resolveVisibilityLabel(value?: Api.Lab.GroupType) {
  return typeList.find(item => item.value === value)?.label || ""
}

function resolveAccessRoleLabel(value?: ProjectRole) {
  return publicAccessRoleList.find(role => role.value === value)?.label || ""
}

async function handleCancel() {
  await nextTick(() => {
    restoreModel()
  })
}

function openVisibilityModal() {
  if (isDefaultProject.value) {
    message.warning($t("page.project.settingsPage.defaultProjectVisibilityHint"))
    return
  }
  visibilityDraft.value = model.value.type
  showVisibilityModal.value = true
}

function closeVisibilityModal() {
  showVisibilityModal.value = false
}

function openAccessRoleModal() {
  accessRoleDraft.value = model.value.public_access_role
  showAccessRoleModal.value = true
}

function closeAccessRoleModal() {
  showAccessRoleModal.value = false
}

function confirmVisibilityDraft() {
  if (!visibilityDraft.value || visibilityDraft.value === model.value.type) {
    showVisibilityModal.value = false
    return
  }
  const fromLabel = resolveVisibilityLabel(model.value.type)
  const toLabel = resolveVisibilityLabel(visibilityDraft.value)
  dialog.warning({
    title: $t("page.project.settingsPage.visibilityChangeTitle"),
    content: $t("page.project.settingsPage.visibilityChangeDescription", { from: fromLabel, to: toLabel }),
    closable: false,
    positiveText: $t("common.confirm"),
    positiveButtonProps: { size: "medium", type: "error" },
    negativeText: $t("common.cancel"),
    negativeButtonProps: { size: "medium" },
    onPositiveClick: async () => {
      const projectId = projectInfo.value?.id
      if (!projectId || Array.isArray(projectId)) {
        return
      }

      visibilitySubmitting.value = true
      const { error } = await putProjectInfo({
        projectId,
        type: visibilityDraft.value,
      })
      visibilitySubmitting.value = false

      if (error) {
        message.error($t("page.project.settingsPage.updateError"))
        return
      }

      model.value.type = visibilityDraft.value
      if (projectInfo.value) {
        projectInfo.value.type = visibilityDraft.value
      }
      message.success($t("page.project.settingsPage.updateSuccess"))
      showVisibilityModal.value = false
    },
  })
}

async function confirmAccessRoleDraft() {
  if (!accessRoleDraft.value || accessRoleDraft.value === model.value.public_access_role) {
    showAccessRoleModal.value = false
    return
  }

  const fromLabel = resolveAccessRoleLabel(model.value.public_access_role)
  const toLabel = resolveAccessRoleLabel(accessRoleDraft.value)
  dialog.warning({
    title: $t("page.project.settingsPage.accessRoleChangeTitle"),
    content: $t("page.project.settingsPage.accessRoleChangeDescription", { from: fromLabel, to: toLabel }),
    closable: false,
    positiveText: $t("common.confirm"),
    positiveButtonProps: { size: "medium", type: "error" },
    negativeText: $t("common.cancel"),
    negativeButtonProps: { size: "medium" },
    onPositiveClick: async () => {
      const projectId = projectInfo.value?.id
      if (!projectId || Array.isArray(projectId)) {
        return
      }

      accessRoleSubmitting.value = true
      const { error } = await putProjectInfo({
        projectId,
        publicAccessRole: accessRoleDraft.value,
      })
      accessRoleSubmitting.value = false

      if (error) {
        message.error($t("page.project.settingsPage.updateError"))
        return
      }

      model.value.public_access_role = accessRoleDraft.value
      if (projectInfo.value) {
        projectInfo.value.public_access_role = accessRoleDraft.value
      }
      message.success($t("page.project.settingsPage.updateSuccess"))
      showAccessRoleModal.value = false
    },
  })
}

async function submitGeneralUpdate(projectId: string) {
  startSubmit()

  const { description, name, logo } = model.value
  const { data, error } = await putProjectInfo({
    projectId,
    description,
    name,
    avatar: logo,
  })

  endSubmit()

  if (error) {
    message.error($t("page.project.settingsPage.updateError"))
  }
  else {
    message.success($t("page.project.settingsPage.updateSuccess"))
    fetchProjectInfoById(projectId.toString(), () => {
      message.error($t("page.project.settingsPage.fetchUpdatedError"))
    })
  }
}

async function loadSubprojects() {
  const currentProjectId = projectInfo.value?.id
  const currentLabId = projectInfo.value?.lab_id
  if (!currentProjectId || !currentLabId) {
    subprojects.value = []
    return
  }

  startSubprojectsLoading()
  try {
    const data = await fetchProjectList({
      labId: currentLabId,
      parentProjectId: currentProjectId,
      page: 1,
      pageSize: 999,
    })
    subprojects.value = (data?.projects || []).filter(item => item.parent_project_id === currentProjectId)
  }
  catch (error) {
    subprojects.value = []
    message.error((error as Error).message)
  }
  finally {
    endSubprojectsLoading()
  }
}

async function handleConfirm() {
  await validate()

  const projectId = projectInfo.value?.id
  if (!projectId || Array.isArray(projectId)) {
    return
  }

  if (isDefaultProject.value && model.value.type !== initValue.value.type) {
    message.warning($t("page.project.settingsPage.defaultProjectVisibilityHint"))
    return
  }

  const isNotChanged = !isGeneralDirty.value

  if (isNotChanged) {
    dialog.warning({
      title: $t("page.project.settingsPage.noChangesTitle"),
      content: $t("page.project.settingsPage.noChangesDescription"),
      closable: false,
      positiveText: $t("common.close"),
      positiveButtonProps: { size: "medium" },
      negativeText: $t("common.cancel"),
      negativeButtonProps: { size: "medium" },
      onPositiveClick: () => {
        fetchProjectInfoById(projectId.toString(), () => {
          message.error($t("page.project.settingsPage.fetchError"))
        })
      },
    })
    return
  }

  await submitGeneralUpdate(projectId.toString())
}

const fileRef = ref<File | null>(null)
const { routerPushByKey } = useRouterPush()

// Delete modal states
const showDeleteModal = ref(false)
const deleteConfirmationText = ref("")
const { loading: deleting, startLoading: startDeleting, endLoading: endDeleting } = useLoading()

// Computed property to validate delete confirmation
const isDeleteConfirmationValid = computed(() => {
  return deleteConfirmationText.value === "DELETE"
})

function handleDelete() {
  if (isDefaultProject.value) {
    message.warning($t("page.project.settingsPage.defaultProjectDeleteHint"))
    return
  }
  showDeleteModal.value = true
}

function cancelDelete() {
  showDeleteModal.value = false
  deleteConfirmationText.value = ""
}

async function confirmDelete() {
  if (!projectInfo.value || !isDeleteConfirmationValid.value) {
    return
  }

  const { id, lab_uid } = projectInfo.value

  startDeleting()

  const { data, error } = await deleteProject(id)

  endDeleting()

  if (error) {
    message.error($t("page.project.settingsPage.deleteError"))
  }
  else {
    message.success($t("page.project.settingsPage.deleteSuccess"))
    showDeleteModal.value = false
    deleteConfirmationText.value = ""
    routerPushByKey("lab-projects", { params: { labUid: lab_uid } })
  }
}

async function handleCreateSubproject(project: Api.Project.MyProjectInfo) {
  await loadSubprojects()
  await routerPushByKey("project-protocols", {
    params: {
      labUid: project.lab_uid,
      projectUid: project.uid,
    },
  })
}

watch(projectInfo, async (val) => {
  if (val) {
    model.value = { ...initValue.value }
    formRef.value?.restoreValidation()
    await loadSubprojects()
  }
  else {
    subprojects.value = []
  }
}, { immediate: true })
</script>

<style scoped lang="sass">
:deep(.n-base-selection-tags)
  justify-content: flex-start!important
  align-items: start!important
  flex-direction: column!important

:deep(.n-form-item-label)
  font-weight: 500!important
  color: rgb(55 65 81)!important

:deep(.dark .n-form-item-label)
  color: rgb(229 231 235)!important

:deep(.n-input)
  border-radius: 0.5rem!important

:deep(.n-input__textarea)
  border-radius: 0.5rem!important

:deep(.n-radio)
  align-items: flex-start!important

:deep(.n-radio__dot)
  margin-top: 0.125rem!important
</style>

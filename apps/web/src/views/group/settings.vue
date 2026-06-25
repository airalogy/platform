<template>
  <n-form
    v-if="groupInfo"
    ref="formRef"
    :model="model"
    :rules="rules"
    size="large"
    label-width="auto"
    class="size-full flex-1 px-10"
  >
    <!-- General Settings -->
    <settings-card
      title="General"
      description="Manage your group's basic information and preferences"
    >
      <!-- Logo Upload Section -->
      <!-- <n-form-item label="Group Logo" path="logo">
        <div class="flex flex-col space-y-2">
          <form-upload-file
            ref="logoUploadRef"
            :default-file-list="defaultFileList"
            :upload-props="{ accept: 'image/*', showRemoveButton: true }"
            @update:file="handleSelectLogo"
            @uploaded:file="handleUploadedLogo"
          />
          <p class="text-xs text-gray-500">
            Upload a logo for your group. Recommended size: 200x200px
          </p>
        </div>
      </n-form-item> -->

      <!-- Group Name Section -->
      <n-form-item label="Group Name" path="name">
        <n-input
          v-model:value="model.name"
          type="text"
          :maxlength="30"
          required
          show-count
          placeholder="Enter group name"
          class="!rounded-lg"
        />
      </n-form-item>

      <!-- Description Section -->
      <n-form-item label="Description" path="description">
        <n-input
          v-model:value="model.description"
          type="textarea"
          :maxlength="128"
          :autosize="{ minRows: 3, maxRows: 6 }"
          show-count
          placeholder="Describe your group and its purpose"
          class="!rounded-lg"
        />
      </n-form-item>
    </settings-card>

    <!-- Danger Zone -->
    <div class="mb-4 border-t border-gray-200" />
    <settings-card
      title="Danger Zone"
      description="Please proceed with caution"
      :is-danger="true"
    >
      <!-- Group Type Section -->
      <!-- <n-form-item label="Group Visibility" path="type">
        <n-radio-group v-model:value="model.type" class="flex space-x-3">
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
      </n-form-item>
      <div class="my-4 border-t border-gray-200" /> -->

      <!-- Remove Project from Group -->
      <div>
        <h4 class="text-4 font-medium">
          Manage Projects
        </h4>
        <span class="color-text-secondary">
          Remove projects from this group. This action cannot be undone.
        </span>
      </div>
      <n-list bordered class="mt-4">
        <template #header>
          <h3 class="text-lg font-medium">
            Projects in this Group
          </h3>
        </template>
        <n-list-item v-for="project in projects" :key="project.id">
          <div class="flex items-center">
            <div class="flex-1">
              <p class="font-medium">
                {{ project.name }}
              </p>
              <p class="text-sm color-text-secondary">
                {{ project.description }}
              </p>
            </div>
            <n-button type="error" size="small" @click="handleRemoveProject(project.id)">
              Remove
            </n-button>
          </div>
        </n-list-item>
        <n-empty v-if="!projects.length" description="No projects in this group" class="py-4" />
      </n-list>

      <div class="my-4 border-t border-gray-200" />

      <div class="flex items-center">
        <div>
          <h4 class="text-4">
            Delete group
          </h4>
          <span class="color-text-secondary">
            Once the group is deleted, all data will be permanently erased and cannot be recovered.
            Please proceed with caution.
          </span>
        </div>
        <n-button type="error" class="ml-auto" @click="handleDelete">
          DELETE
        </n-button>
      </div>
    </settings-card>

    <!-- Action Buttons -->
    <div class="flex items-center justify-end border-t border-gray-200 pt-6 space-x-3">
      <n-button
        size="medium"
        :disabled="submitting"
        @click="handleCancel"
      >
        Cancel
      </n-button>
      <n-button
        size="medium"
        type="primary"
        :disabled="submitting"
        :loading="submitting"
        class="!px-6"
        @click="handleConfirm"
      >
        Save Changes
      </n-button>
    </div>
  </n-form>

  <!-- Delete Confirmation Modal -->
  <delete-confirmation-modal
    :show="showDeleteModal"
    entity-name="Group"
    :item-name="groupInfo?.name || ''"
    :delete-confirmation-text="deleteConfirmationText"
    :is-delete-confirmation-valid="isDeleteConfirmationValid"
    :deleting="deleting"
    @update:delete-confirmation-text="deleteConfirmationText = $event"
    @confirm="confirmDelete"
    @cancel="cancelDelete"
  />
</template>

<script setup lang="ts">
import type { SelectOption } from "naive-ui/es/select"
import { DeleteConfirmationModal, SettingsCard, useLogoUpload } from "@/components/common/settings"
import { useFormRules, useLoading, useNaiveForm } from "@/composables"
import { deleteGroup, deleteGroupsProjects, fetchGroupsProjectList, putGroupsInfo } from "@/service/api/groups"
import { useGroupInfoStore } from "@/views/group/hooks/useGroupInfoStore"
import { useClosableMessage } from "@airalogy/composables"
import { isEqual } from "lodash-es"
import { useDialog } from "naive-ui"
import { useRouterPush } from "../../composables/useRouterPush"

const { groupInfo, fetchGroupInfo } = useGroupInfoStore()!

interface FormModel {
  name?: string
  description?: string
  type?: Api.Lab.GroupType
  logo?: string
}

const { defaultRequiredRule } = useFormRules()
const { formRef, validate } = useNaiveForm()

const rules: Partial<Record<keyof FormModel, App.Global.FormRule[]>> = {
  name: [
    defaultRequiredRule,
    {
      min: 1,
      max: 40,
      message: "Group name must be between 1 and 40 characters long",
      trigger: ["change", "blur"],
    },
    {
      pattern: /^[\w\s-]*$/,
      message: "Group name can only contain letters, numbers, spaces, and hyphens",
      trigger: ["change", "blur"],
    },
    {
      validator: (rule, value, callback) => {
        if (/^[_\s-]|[_\s-]$/.test(value)) {
          return new Error("Group name should not start or end with special characters")
        }
        if (/[_\s-]{2,}/.test(value)) {
          return new Error("Special characters cannot appear consecutively")
        }
        return true
      },
      trigger: ["change", "blur"],
    },
  ],
  type: [defaultRequiredRule],
}

const memberOptions = ref<SelectOption[]>([])

const typeList = [
  {
    label: "Public",
    value: 0,
    description: "Anyone can view this group and its contents",
  },
  {
    label: "Private",
    value: 1,
    description: "Only group members can view and access this group",
  },
]

const initValue = computed(
  (): FormModel => ({
    name: groupInfo.value?.name,
    description: groupInfo.value?.description,
    type: groupInfo.value?.type,
    logo: groupInfo.value?.avatar || undefined,
  }),
)

const model = ref<FormModel>({
  name: "",
  description: "",
  type: undefined,
  logo: undefined,
})

// Logo upload
// const logoUrlValue = computed(() => groupInfo.value?.avatar_url || undefined)
const logoUrlValue = computed(() => undefined)
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

function restoreModel() {
  model.value = { ...initValue.value }
  memberOptions.value = []
  formRef.value?.restoreValidation()
}

const { loading: submitting, startLoading: startSubmit, endLoading: endSubmit } = useLoading()

const dialog = useDialog()
const message = useClosableMessage()

async function handleCancel() {
  await nextTick(() => {
    restoreModel()
  })
}

async function handleConfirm() {
  await validate()

  const groupId = groupInfo.value?.id
  if (!groupId || Array.isArray(groupId)) {
    return
  }

  const isNotChanged = isEqual(model.value, initValue.value)

  if (isNotChanged) {
    dialog.warning({
      title: "No Changes Detected",
      content: "Group information has not been modified.",
      closable: false,
      positiveText: "Close",
      positiveButtonProps: { size: "medium" },
      negativeText: "Cancel",
      negativeButtonProps: { size: "medium" },
      onPositiveClick: () => {
        fetchGroupInfo(groupId.toString(), () => {
          message.error("Failed to fetch group info")
        })
      },
    })
    return
  }

  startSubmit()

  const { description, name, type, logo } = model.value
  const { data, error } = await putGroupsInfo({
    groupId,
    description,
    name,
    avatar: logo,
  })

  endSubmit()

  if (error) {
    message.error("Failed to update group information. Please try again.")
  }
  else {
    message.success("Group information updated successfully.")
    fetchGroupInfo(groupId.toString(), () => {
      message.error("Failed to fetch updated group info")
    })
  }
}

const { routerPushByKey } = useRouterPush()

const projects = ref<Api.Project.MyProjectInfo[]>([])
const { loading: projectsLoading, startLoading: startProjectsLoading, endLoading: endProjectsLoading } = useLoading()

async function getProjects() {
  const groupId = groupInfo.value?.id
  if (!groupId)
    return

  startProjectsLoading()
  const data = await fetchGroupsProjectList(groupId)
  if (data) {
    projects.value = data.projects
  }
  endProjectsLoading()
}

async function handleRemoveProject(projectId: string) {
  const groupId = groupInfo.value?.id
  if (!groupId)
    return

  dialog.warning({
    title: "Remove Project",
    content: "Are you sure you want to remove this project from the group?",
    positiveText: "Remove",
    negativeText: "Cancel",
    onPositiveClick: async () => {
      const { error } = await deleteGroupsProjects(groupId, projectId)
      if (error) {
        message.error("Failed to remove project.")
      }
      else {
        message.success("Project removed successfully.")
        getProjects()
      }
    },
  })
}

// Delete modal states
const showDeleteModal = ref(false)
const deleteConfirmationText = ref("")
const { loading: deleting, startLoading: startDeleting, endLoading: endDeleting } = useLoading()

// Computed property to validate delete confirmation
const isDeleteConfirmationValid = computed(() => {
  return deleteConfirmationText.value === "DELETE"
})

function handleDelete() {
  showDeleteModal.value = true
}

function cancelDelete() {
  showDeleteModal.value = false
  deleteConfirmationText.value = ""
}

async function confirmDelete() {
  if (!groupInfo.value || !isDeleteConfirmationValid.value) {
    return
  }

  const { id, lab_uid } = groupInfo.value

  startDeleting()

  const success = await deleteGroup(id)

  endDeleting()

  if (!success) {
    message.error("Failed to delete group. Please try again.")
  }
  else {
    message.success("Group deleted successfully.")
    showDeleteModal.value = false
    deleteConfirmationText.value = ""
    routerPushByKey("lab-groups", { params: { labUid: lab_uid } })
  }
}

watch(groupInfo, (val) => {
  if (val) {
    model.value = { ...initValue.value }
    formRef.value?.restoreValidation()
    getProjects()
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

<template>
  <div class="size-full flex-1 px-10">
    <n-form
      v-if="labInfo"
      ref="formRef"
      :model="model"
      :rules="rules"
      size="large"
      label-width="auto"
      class="size-full flex-1"
    >
      <!-- General Settings -->
      <settings-card
        :title="$t('page.labs.settingsPage.generalTitle')"
        :description="$t('page.labs.settingsPage.generalDescription')"
      >
        <!-- Logo Upload Section -->
        <n-form-item :label="$t('page.labs.settingsPage.logoLabel')" path="logo">
          <div class="flex flex-col space-y-2">
            <form-upload-file
              ref="logoUploadRef"
              :default-file-list="defaultFileList"
              :upload-props="{ accept: 'image/*', showRemoveButton: true }"
              @update:file="handleSelectLogo"
              @uploaded:file="handleUploadedLogo"
            />
            <p class="text-xs text-gray-500">
              {{ $t("page.labs.settingsPage.logoHint") }}
            </p>
          </div>
        </n-form-item>

        <!-- Lab ID Section -->
        <n-form-item :label="$t('page.labs.settingsPage.labIdLabel')">
          <div class="flex flex-col space-y-2">
            <n-input
              :value="labInfo?.uid || ''"
              type="text"
              disabled
              class="!rounded-lg"
            />
            <p class="text-xs text-gray-500">
              {{ $t("page.labs.settingsPage.labIdHint") }}
            </p>
          </div>
        </n-form-item>

        <!-- Lab Name Section -->
        <n-form-item :label="$t('page.labs.settingsPage.nameLabel')" path="displayName">
          <n-input
            v-model:value="model.displayName"
            type="text"
            :maxlength="40"
            required
            show-count
            :placeholder="$t('page.labs.settingsPage.namePlaceholder')"
            class="!rounded-lg"
          />
        </n-form-item>

        <!-- Description Section -->
        <n-form-item :label="$t('page.labs.settingsPage.descriptionLabel')" path="description">
          <n-input
            v-model:value="model.description"
            type="textarea"
            :maxlength="128"
            :autosize="{ minRows: 3, maxRows: 6 }"
            show-count
            :placeholder="$t('page.labs.settingsPage.descriptionPlaceholder')"
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
              :disabled="submitting || !isDirty"
              :loading="submitting"
              class="!px-6"
              @click="handleConfirmWrapper"
            >
              {{ $t("page.labs.settingsPage.saveAction") }}
            </n-button>
          </div>
        </template>
      </settings-card>

      <!-- Danger Zone -->
      <div class="mb-4 mt-6 border-t border-gray-200" />
      <settings-card
        :title="$t('page.labs.settingsPage.dangerTitle')"
        :description="$t('page.labs.settingsPage.dangerDescription')"
        :is-danger="true"
      >
        <div v-if="canDeleteLab" class="flex flex-col gap-4">
          <div class="flex items-center gap-4">
            <div>
              <h4 class="text-4">
                {{ $t("page.labs.settingsPage.deleteTitle") }}
              </h4>
              <span class="color-text-secondary">
                {{ $t("page.labs.settingsPage.deleteDescription") }}
              </span>
            </div>
            <n-button
              type="error"
              class="ml-auto"
              :disabled="isLabDeleteBlocked"
              @click="handleDelete"
            >
              {{ $t("common.delete") }}
            </n-button>
          </div>

          <div
            class="border rounded-lg px-4 py-3 text-sm"
            :class="isLabDeleteBlocked ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-red-200 bg-red-50 text-red-900'"
          >
            <div class="font-600">
              {{ $t("page.labs.settingsPage.deleteRequirementsTitle") }}
            </div>
            <p class="mt-1">
              {{ deleteStatusHint }}
            </p>
            <ul v-if="isLabDeleteBlocked" class="mt-3 list-disc pl-5">
              <li
                v-for="reason in deleteBlockingReasons"
                :key="reason"
              >
                {{ reason }}
              </li>
            </ul>
          </div>

          <div
            v-if="showForceDeleteAction"
            class="border border-red-200 rounded-lg bg-red-50 px-4 py-4 text-red-950"
          >
            <div class="flex items-center gap-4">
              <div>
                <h4 class="text-4">
                  {{ $t("page.labs.settingsPage.forceDeleteTitle") }}
                </h4>
                <span class="color-text-secondary">
                  {{ $t("page.labs.settingsPage.forceDeleteDescription") }}
                </span>
              </div>
              <n-button
                type="error"
                secondary
                class="ml-auto"
                :disabled="isForceDeleteActionDisabled"
                :loading="forceDeletePreviewLoading"
                @click="openForceDeleteModal"
              >
                {{ $t("page.labs.settingsPage.forceDeleteAction") }}
              </n-button>
            </div>

            <p class="mt-3 text-sm">
              {{ forceDeleteCardHint }}
            </p>
          </div>
        </div>
      </settings-card>
    </n-form>

    <!-- Delete Confirmation Modal -->
    <delete-confirmation-modal
      :show="showDeleteModal"
      :entity-name="$t('page.labs.settingsPage.deleteEntityName')"
      :item-name="labInfo?.name || ''"
      :delete-confirmation-text="deleteConfirmationText"
      :is-delete-confirmation-valid="isDeleteConfirmationValid"
      :deleting="deleting"
      :extra-warning="$t('page.labs.settingsPage.deleteModalWarning')"
      @update:delete-confirmation-text="deleteConfirmationText = $event"
      @confirm="confirmDelete"
      @cancel="cancelDelete"
    />

    <n-modal
      :show="showForceDeleteModal"
      preset="card"
      class="max-w-[calc(100vw-32px)] w-180"
      :title="$t('page.labs.settingsPage.forceDeletePreviewTitle')"
      :mask-closable="false"
      @update:show="handleForceDeleteModalUpdate"
    >
      <div class="flex flex-col gap-4">
        <p class="text-sm color-text-secondary">
          {{ $t("page.labs.settingsPage.forceDeletePreviewDescription") }}
        </p>

        <div class="grid grid-cols-2 gap-3 md:grid-cols-3">
          <div
            v-for="item in forceDeleteImpactItems"
            :key="item.key"
            class="border border-red-200 rounded-lg bg-white px-3 py-3"
          >
            <div class="text-xs color-text-secondary">
              {{ item.label }}
            </div>
            <div class="mt-1 text-5 font-600">
              {{ item.value }}
            </div>
          </div>
        </div>

        <n-form label-placement="top">
          <n-form-item :label="$t('page.labs.settingsPage.forceDeleteUidLabel')">
            <n-input
              v-model:value="forceDeleteUidConfirmation"
              :placeholder="$t('page.labs.settingsPage.forceDeleteUidPlaceholder')"
            />
          </n-form-item>
        </n-form>

        <n-checkbox v-model:checked="forceDeleteIrreversibleConfirmed">
          {{ $t("page.labs.settingsPage.forceDeleteCheckbox") }}
        </n-checkbox>

        <div class="border border-red-200 rounded-lg bg-red-100 px-4 py-3 text-sm">
          {{ $t("page.labs.settingsPage.forceDeleteFinalWarning") }}
        </div>

        <div class="flex items-center justify-end gap-2">
          <n-button :disabled="forceDeleteSubmitting" @click="closeForceDeleteModal">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button
            type="error"
            :disabled="!isForceDeleteConfirmationValid || forceDeleteSubmitting"
            :loading="forceDeleteSubmitting"
            @click="confirmForceDelete"
          >
            {{ $t("page.labs.settingsPage.forceDeleteAction") }}
          </n-button>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { AxiosError } from "axios"
import {
  type BaseFormModel,
  DeleteConfirmationModal,
  SettingsCard,
  useDeleteConfirmation,
  useLogoUpload,
  useSettingsForm,
} from "@/components/common/settings"
import { useLabPermissions } from "@/composables/useLabPermissions"
import { useRouterPush } from "@/composables/useRouterPush"
import {
  deleteLab,
  getLabForceDeleteJob,
  getLabForceDeletePreview,
  postLabForceDelete,
  putLabInfo,
} from "@/service/api/labs"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { useOrProvideLabInfoStore } from "./hooks/useLabsInfoStore"

const { labInfo, fetchLabInfoById } = useOrProvideLabInfoStore(null)
const { routerPushByKey } = useRouterPush()
const { canDeleteLab } = useLabPermissions(labInfo)
const message = useClosableMessage()
interface FormModel extends BaseFormModel {
  displayName?: string
}

const initValue = computed(
  (): FormModel => ({
    displayName: labInfo.value?.name,
    description: labInfo.value?.description,
    type: labInfo.value?.type,
    logo: labInfo.value?.logo || undefined,
  }),
)

// Form management
const {
  model,
  formRef,
  submitting,
  isDirty,
  getBaseRules,
  handleCancel,
  handleConfirm,
} = useSettingsForm<FormModel>(
  initValue,
  async (formData) => {
    const labId = labInfo.value?.id
    if (!labId || Array.isArray(labId)) {
      throw new Error("Invalid lab ID")
    }

    const { description, displayName, type, logo } = formData
    return await putLabInfo(labId, {
      description,
      name: displayName,
      type,
      logo,
    })
  },
  () => {
    const labId = labInfo.value?.id
    if (labId && !Array.isArray(labId)) {
      fetchLabInfoById(labId, () => {
        // Error handling is done in the composable
      })
    }
  },
  undefined,
  {
    messages: {
      noChangesTitle: $t("page.labs.settingsPage.noChangesTitle"),
      noChangesDescription: $t("page.labs.settingsPage.noChangesDescription"),
      updateError: $t("page.labs.settingsPage.updateError"),
      updateSuccess: $t("page.labs.settingsPage.updateSuccess"),
      closeText: $t("common.close"),
      cancelText: $t("common.cancel"),
    },
  },
)

// Form validation rules
const rules = {
  ...getBaseRules("Lab"),
  displayName: getBaseRules("Lab").displayName,
}

// Logo upload
const logoUrlValue = computed(() => labInfo.value?.logo_url || undefined)
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

const labCustomProjectsCount = computed(() => {
  return Number(labInfo.value?.custom_projects_count ?? labInfo.value?.projects_count ?? 0)
})

const labDefaultProjectsCount = computed(() => {
  return Number(labInfo.value?.default_projects_count || 0)
})

const labDefaultProjectsProtocolsCount = computed(() => {
  return Number(labInfo.value?.default_projects_protocols_count || 0)
})

const deleteBlockingReasons = computed(() => {
  const reasons: string[] = []

  if (labCustomProjectsCount.value > 0) {
    reasons.push(
      $t("page.labs.settingsPage.deleteBlockedProjects", { count: labCustomProjectsCount.value }),
    )
  }

  if (labDefaultProjectsProtocolsCount.value > 0) {
    reasons.push(
      $t("page.labs.settingsPage.deleteBlockedDefaultProjectProtocols", {
        count: labDefaultProjectsProtocolsCount.value,
      }),
    )
  }

  return reasons
})

const isLabDeleteBlocked = computed(() => {
  return deleteBlockingReasons.value.length > 0
})

const deleteStatusHint = computed(() => {
  if (isLabDeleteBlocked.value) {
    return $t("page.labs.settingsPage.deleteBlockedHint")
  }

  if (labDefaultProjectsCount.value > 0) {
    return $t("page.labs.settingsPage.deleteReadyWithDefaultProjectsHint", {
      count: labDefaultProjectsCount.value,
    })
  }

  return $t("page.labs.settingsPage.deleteReadyHint")
})

const showForceDeleteAction = computed(() => {
  return canDeleteLab.value && isLabDeleteBlocked.value
})

function handleDeleteError(error: unknown) {
  const detail = (error as AxiosError<Api.ErrorResponse>)?.response?.data?.detail

  if (detail === "Lab has projects") {
    message.error($t("page.labs.settingsPage.deleteErrorHasProjects"))
    return
  }

  if (detail === "Default projects contain protocols") {
    message.error($t("page.labs.settingsPage.deleteErrorDefaultProjectsHaveProtocols"))
    return
  }

  if (detail === "Forbidden") {
    message.error($t("page.labs.settingsPage.deleteErrorForbidden"))
    return
  }

  message.error($t("page.labs.settingsPage.deleteError"))
}

const showForceDeleteModal = ref(false)
const forceDeletePreviewLoading = ref(false)
const forceDeleteSubmitting = ref(false)
const forceDeletePreview = ref<Api.Lab.ForceDeletePreview | null>(null)
const forceDeleteUidConfirmation = ref("")
const forceDeleteIrreversibleConfirmed = ref(false)
const activeForceDeleteJob = ref<Api.Lab.ForceDeleteJob | null>(null)
const forceDeletePollTimer = ref<ReturnType<typeof setTimeout> | null>(null)

const isForceDeleteInProgress = computed(() => {
  const status = activeForceDeleteJob.value?.status
  return status === "pending" || status === "running"
})

const isForceDeleteActionDisabled = computed(() => {
  return forceDeletePreviewLoading.value || forceDeleteSubmitting.value || isForceDeleteInProgress.value
})

const isForceDeleteConfirmationValid = computed(() => {
  const expectedUid = labInfo.value?.uid || ""
  return Boolean(forceDeletePreview.value)
    && forceDeleteUidConfirmation.value.trim() === expectedUid
    && forceDeleteIrreversibleConfirmed.value
})

const forceDeleteCardHint = computed(() => {
  if (isForceDeleteInProgress.value) {
    return $t("page.labs.settingsPage.forceDeleteInProgressDescription")
  }

  return $t("page.labs.settingsPage.forceDeleteOwnerHint")
})

const forceDeleteImpactItems = computed(() => {
  const preview = forceDeletePreview.value

  return [
    {
      key: "members",
      label: $t("page.labs.settingsPage.forceDeleteImpactMembers"),
      value: preview?.members ?? 0,
    },
    {
      key: "groups",
      label: $t("page.labs.settingsPage.forceDeleteImpactGroups"),
      value: preview?.groups ?? 0,
    },
    {
      key: "projects_total",
      label: $t("page.labs.settingsPage.forceDeleteImpactProjectsTotal"),
      value: preview?.projects_total ?? 0,
    },
    {
      key: "projects_active",
      label: $t("page.labs.settingsPage.forceDeleteImpactProjectsActive"),
      value: preview?.projects_active ?? 0,
    },
    {
      key: "projects_default",
      label: $t("page.labs.settingsPage.forceDeleteImpactProjectsDefault"),
      value: preview?.projects_default ?? 0,
    },
    {
      key: "protocols_total",
      label: $t("page.labs.settingsPage.forceDeleteImpactProtocolsTotal"),
      value: preview?.protocols_total ?? 0,
    },
    {
      key: "protocols_active",
      label: $t("page.labs.settingsPage.forceDeleteImpactProtocolsActive"),
      value: preview?.protocols_active ?? 0,
    },
    {
      key: "records_total",
      label: $t("page.labs.settingsPage.forceDeleteImpactRecordsTotal"),
      value: preview?.records_total ?? 0,
    },
    {
      key: "records_active",
      label: $t("page.labs.settingsPage.forceDeleteImpactRecordsActive"),
      value: preview?.records_active ?? 0,
    },
    {
      key: "files_total",
      label: $t("page.labs.settingsPage.forceDeleteImpactFilesTotal"),
      value: preview?.files_total ?? 0,
    },
  ]
})

function clearForceDeletePollTimer() {
  if (forceDeletePollTimer.value !== null) {
    clearTimeout(forceDeletePollTimer.value)
    forceDeletePollTimer.value = null
  }
}

function resetForceDeleteConfirmation() {
  forceDeleteUidConfirmation.value = ""
  forceDeleteIrreversibleConfirmed.value = false
}

function closeForceDeleteModal() {
  showForceDeleteModal.value = false
  resetForceDeleteConfirmation()
}

function handleForceDeleteModalUpdate(value: boolean) {
  showForceDeleteModal.value = value
  if (!value) {
    resetForceDeleteConfirmation()
  }
}

function handleForceDeleteError(
  error: unknown,
  context: "preview" | "start" | "status" = "start",
) {
  const detail = (error as AxiosError<Api.ErrorResponse>)?.response?.data?.detail

  if (detail === "Forbidden") {
    message.error($t("page.labs.settingsPage.forceDeleteErrorForbidden"))
    return
  }

  if (detail === "Lab UID confirmation does not match") {
    message.error($t("page.labs.settingsPage.forceDeleteErrorUidMismatch"))
    return
  }

  if (detail === "Irreversible confirmation is required") {
    message.error($t("page.labs.settingsPage.forceDeleteErrorIrreversibleRequired"))
    return
  }

  if (detail === "Lab force delete already in progress") {
    message.error($t("page.labs.settingsPage.forceDeleteErrorAlreadyInProgress"))
    return
  }

  if (detail === "Lab force delete job not found") {
    message.error($t("page.labs.settingsPage.forceDeleteErrorJobNotFound"))
    return
  }

  if (context === "preview") {
    message.error($t("page.labs.settingsPage.forceDeletePreviewError"))
    return
  }

  if (context === "status") {
    message.error($t("page.labs.settingsPage.forceDeleteStatusError"))
    return
  }

  message.error($t("page.labs.settingsPage.forceDeleteError"))
}

function formatForceDeleteFailure(job: Api.Lab.ForceDeleteJob) {
  const reason = job.failure_reason?.trim()
  if (!reason) {
    return $t("page.labs.settingsPage.forceDeleteFailed")
  }

  return `${$t("page.labs.settingsPage.forceDeleteFailedWithReason")}: ${reason}`
}

function scheduleForceDeletePoll() {
  clearForceDeletePollTimer()
  forceDeletePollTimer.value = setTimeout(() => {
    void pollForceDeleteJob()
  }, 2000)
}

async function pollForceDeleteJob() {
  const labId = labInfo.value?.id
  const jobId = activeForceDeleteJob.value?.id

  if (!labId || Array.isArray(labId) || !jobId) {
    clearForceDeletePollTimer()
    return
  }

  try {
    const job = await getLabForceDeleteJob(labId, jobId, { showError: false })
    activeForceDeleteJob.value = job

    if (job.status === "pending" || job.status === "running") {
      scheduleForceDeletePoll()
      return
    }

    clearForceDeletePollTimer()

    if (job.status === "succeeded") {
      message.success($t("page.labs.settingsPage.forceDeleteSuccess"))
      await routerPushByKey("labs-my")
      return
    }

    message.error(formatForceDeleteFailure(job))
  }
  catch (error) {
    clearForceDeletePollTimer()
    handleForceDeleteError(error, "status")
  }
}

async function openForceDeleteModal() {
  const labId = labInfo.value?.id
  if (!labId || Array.isArray(labId)) {
    throw new Error("Invalid lab ID")
  }

  forceDeletePreviewLoading.value = true
  try {
    forceDeletePreview.value = await getLabForceDeletePreview(labId, { showError: false })
    resetForceDeleteConfirmation()
    showForceDeleteModal.value = true
  }
  catch (error) {
    handleForceDeleteError(error, "preview")
  }
  finally {
    forceDeletePreviewLoading.value = false
  }
}

async function confirmForceDelete() {
  const labId = labInfo.value?.id
  const labUid = labInfo.value?.uid
  if (!labId || Array.isArray(labId) || !labUid) {
    throw new Error("Invalid lab ID")
  }

  if (!isForceDeleteConfirmationValid.value) {
    return
  }

  forceDeleteSubmitting.value = true
  try {
    const job = await postLabForceDelete(
      labId,
      {
        labUid,
        confirmIrreversible: true,
      },
      { showError: false },
    )
    activeForceDeleteJob.value = job
    closeForceDeleteModal()
    message.info($t("page.labs.settingsPage.forceDeleteStarted"))
    await pollForceDeleteJob()
  }
  catch (error) {
    handleForceDeleteError(error, "start")
  }
  finally {
    forceDeleteSubmitting.value = false
  }
}

// Delete functionality
const {
  showDeleteModal,
  deleteConfirmationText,
  deleting,
  isDeleteConfirmationValid,
  handleDelete,
  cancelDelete,
  confirmDelete,
} = useDeleteConfirmation(
  async () => {
    const labId = labInfo.value?.id
    if (!labId || Array.isArray(labId)) {
      throw new Error("Invalid lab ID")
    }

    const result = await deleteLab(labId, { showError: false })
    return { data: result, error: result ? null : new Error("Delete failed") }
  },
  "Lab",
  () => {
    // Navigate to my labs page after successful deletion
    routerPushByKey("labs-my")
  },
  handleDeleteError,
)

// Handle confirm with entity name
async function handleConfirmWrapper() {
  await handleConfirm($t("page.labs.settingsPage.infoName"))
}

onBeforeUnmount(() => {
  clearForceDeletePollTimer()
})
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
</style>

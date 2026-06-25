<template>
  <div class="size-full flex-1 px-10">
    <n-form
      v-if="protocolInfo"
      ref="formRef"
      :model="model"
      :rules="rules"
      size="large"
      label-width="auto"
      class="size-full flex-1"
    >
      <n-alert
        v-if="isManagingOthersProtocol"
        type="warning"
        show-icon
        bordered
        :title="$t('page.protocol.settings.adminViewTitle')"
        class="mb-4"
      >
        <div class="space-y-2">
          <p class="font-medium">
            {{ $t("page.protocol.settings.adminViewNotice") }}
          </p>
          <p class="text-sm text-amber-900">
            {{ $t("page.protocol.settings.adminViewDetail") }}
          </p>
          <div class="flex flex-wrap gap-2">
            <n-tag type="warning" size="small" bordered>
              {{ $t("page.protocol.settings.adminViewActionEditInfo") }}
            </n-tag>
            <n-tag type="warning" size="small" bordered>
              {{ $t("page.protocol.settings.adminViewActionEditEnv") }}
            </n-tag>
            <n-tag type="warning" size="small" bordered>
              {{ $t("page.protocol.settings.adminViewActionDelete") }}
            </n-tag>
          </div>
        </div>
      </n-alert>
      <!-- General Settings -->
      <settings-card
        :title="$t('page.protocol.settings.basicInfoTitle')"
        :description="$t('page.protocol.settings.basicInfoDescription')"
      >
        <!-- Protocol ID -->
        <n-form-item :label="$t('page.protocol.settings.protocolIdLabel')">
          <n-input
            :value="protocolIdDisplay"
            disabled
            class="font-mono !rounded-lg"
          />
        </n-form-item>

        <!-- Protocol Version -->
        <n-form-item :label="$t('page.protocol.settings.protocolVersionLabel')">
          <n-input
            :value="protocolVersionDisplay"
            disabled
            class="font-mono !rounded-lg"
          />
        </n-form-item>

        <!-- Protocol Name -->
        <n-form-item :label="$t('page.protocol.protocolName')" path="name">
          <n-input
            v-model:value="model.name"
            :disabled="!hasEditPermission"
            type="text"
            :maxlength="50"
            show-count
            :placeholder="$t('page.protocol.settings.protocolNamePlaceholder')"
            class="!rounded-lg"
          />
        </n-form-item>

        <!-- Description -->
        <n-form-item :label="$t('common.description')" path="description">
          <n-input
            v-model:value="model.description"
            :disabled="!hasEditPermission"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 6 }"
            :maxlength="500"
            show-count
            :placeholder="$t('page.protocol.settings.descriptionPlaceholder')"
            class="!rounded-lg"
          />
        </n-form-item>

        <!-- Disciplines -->
        <n-form-item :label="$t('common.disciplines')" path="disciplines">
          <n-dynamic-tags
            v-model:value="model.disciplines"
            :max="10"
            :disabled="!hasEditPermission"
            :input-props="{ placeholder: $t('page.protocol.settings.disciplinesPlaceholder') }"
          />
        </n-form-item>

        <!-- Keywords -->
        <n-form-item :label="$t('common.keywords')" path="keywords">
          <n-dynamic-tags
            v-model:value="model.keywords"
            :max="20"
            :disabled="!hasEditPermission"
            :input-props="{ placeholder: $t('page.protocol.settings.keywordsPlaceholder') }"
          />
        </n-form-item>

        <!-- License -->
        <n-form-item :label="$t('common.license')" path="license">
          <n-select
            v-model:value="model.license"
            :disabled="!hasEditPermission"
            :options="licenseOptions"
            filterable
            tag
            :placeholder="$t('page.protocol.settings.licensePlaceholder')"
            class="w-fit"
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
              :disabled="submitting || !hasEditPermission || !isDirty"
              :loading="submitting"
              class="!px-6"
              @click="handleConfirm($t('page.protocol.info'))"
            >
              {{ $t("page.protocol.settings.saveChanges") }}
            </n-button>
          </div>
        </template>
      </settings-card>

      <!-- Danger Zone -->
      <div class="mb-4 mt-6 border-t border-gray-200" />
      <settings-card
        :title="$t('page.protocol.settings.dangerTitle')"
        :description="$t('page.protocol.settings.dangerDescription')"
        :is-danger="true"
      >
        <!-- Environment Variables -->
        <n-form-item :label="$t('page.protocol.settings.envTitle')" path="env" :show-feedback="false" class="mb-3" label-class="font-semibold">
          <div class="w-full space-y-3">
            <div>
              <p class="text-sm text-gray-600">
                {{ $t("page.protocol.settings.envDescription") }}
              </p>
            </div>

            <template v-if="!hasEnvPermission">
              <n-tag type="warning" size="small">
                <template #icon>
                  <n-icon><icon-tabler-lock /></n-icon>
                </template>
                {{ $t("page.protocol.settings.envRestrictedTitle") }}
              </n-tag>

              <n-alert
                type="warning"
                show-icon
              >
                <template #icon>
                  <n-icon><icon-tabler-shield-lock /></n-icon>
                </template>
                {{ $t("page.protocol.settings.envRestrictedDescription") }}
              </n-alert>

              <div v-if="hasEnvVars" class="relative">
                <n-input
                  :value="envVarsMask"
                  disabled
                  type="textarea"
                  :autosize="{ minRows: 4, maxRows: 12 }"
                  class="text-sm font-mono !rounded-lg"
                />
                <div class="absolute inset-0 flex items-center justify-center rounded-lg bg-black bg-opacity-5">
                  <div class="text-center">
                    <n-icon size="32" class="mb-2 text-gray-400">
                      <icon-tabler-eye-off />
                    </n-icon>
                    <p class="text-sm text-gray-500">
                      {{ $t("page.protocol.settings.envHidden") }}
                    </p>
                  </div>
                </div>
              </div>

              <n-empty v-else :description="$t('page.protocol.settings.envEmpty')" />
            </template>

            <template v-else>
              <template v-if="hasEnvVars">
                <div class="rounded-lg bg-blue-50 p-3">
                  <div class="flex items-start space-x-2">
                    <n-icon class="mt-0.5 text-blue-600" size="16">
                      <icon-tabler-info-circle />
                    </n-icon>
                    <div class="text-sm text-blue-800">
                      <p class="font-bio mb-1">
                        {{ $t("page.protocol.settings.envDetectedTitle") }}
                      </p>
                      <p>{{ $t("page.protocol.settings.envDetectedDescription") }}</p>
                    </div>
                  </div>
                </div>
              </template>

              <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
                <span v-if="hasEnvVars" class="text-sm text-gray-600">
                  {{ $t("page.protocol.settings.envHiddenForSecurity") }}
                </span>
                <span v-else class="text-sm text-gray-500">
                  {{ $t("page.protocol.settings.envEmpty") }}
                </span>
                <div class="flex flex-wrap items-center gap-2">
                  <n-button
                    text
                    type="primary"
                    size="small"
                    :disabled="!hasEnvVars || !showEnvValues"
                    @click="handleCopyEnv"
                  >
                    <template #icon>
                      <n-icon>
                        <icon-tabler-check v-if="isEnvCopied" />
                        <icon-tabler-copy v-else />
                      </n-icon>
                    </template>
                    {{ isEnvCopied ? $t("page.protocol.settings.copied") : $t("page.protocol.settings.copy") }}
                  </n-button>
                  <n-button
                    text
                    type="primary"
                    size="small"
                    :disabled="!hasEnvVars"
                    @click="showEnvValues = !showEnvValues"
                  >
                    <template #icon>
                      <n-icon>
                        <icon-tabler-eye v-if="!showEnvValues" />
                        <icon-tabler-eye-off v-else />
                      </n-icon>
                    </template>
                    {{ showEnvValues ? $t("page.protocol.settings.hideValues") : $t("page.protocol.settings.showValues") }}
                  </n-button>
                  <n-button
                    v-if="!isEnvEditing"
                    type="error"
                    size="small"
                    :disabled="!hasEnvPermission"
                    @click="startEnvEdit"
                  >
                    {{ $t("page.protocol.settings.envEdit") }}
                  </n-button>
                  <template v-else>
                    <n-button
                      size="small"
                      :disabled="envSaving"
                      @click="cancelEnvEdit"
                    >
                      {{ $t("common.cancel") }}
                    </n-button>
                    <n-button
                      type="error"
                      size="small"
                      :loading="envSaving"
                      :disabled="envSaving || !envDirty"
                      @click="handleEnvSave"
                    >
                      {{ $t("page.protocol.settings.envSave") }}
                    </n-button>
                  </template>
                </div>
              </div>

              <n-input
                :value="envDisplayValue"
                :disabled="envReadOnly || submitting"
                type="textarea"
                :autosize="{ minRows: 4, maxRows: 12 }"
                :placeholder="$t('page.protocol.settings.envPlaceholder')"
                class="text-sm font-mono !rounded-lg"
                @input="handleEnvInput"
              />
            </template>
          </div>
        </n-form-item>

        <!-- Delete Protocol -->
        <div class="flex items-center justify-between">
          <div>
            <h4 class="text-base text-gray-900 font-medium">
              {{ $t("page.protocol.settings.deleteTitle") }}
            </h4>
            <p class="text-sm text-gray-600">
              {{ $t("page.protocol.settings.deleteDescription") }}
            </p>
          </div>
          <n-button
            type="error"
            :disabled="!hasDeletePermission"
            @click="handleDelete"
          >
            {{ $t("common.delete") }}
          </n-button>
        </div>
      </settings-card>
    </n-form>

    <!-- Delete Confirmation Modal -->
    <delete-confirmation-modal
      :show="showDeleteModal"
      :entity-name="$t('common.protocol')"
      :item-name="protocolInfo?.name || ''"
      :delete-confirmation-text="deleteConfirmationText"
      :is-delete-confirmation-valid="isDeleteConfirmationValid"
      :deleting="deleting"
      :extra-warning="deleteExtraWarning"
      @update:delete-confirmation-text="deleteConfirmationText = $event"
      @confirm="confirmDelete"
      @cancel="cancelDelete"
    />
  </div>
</template>

<script setup lang="ts">
import {
  type BaseFormModel,
  DeleteConfirmationModal,
  SettingsCard,
  useDeleteConfirmation,
  useSettingsForm,
} from "@/components/common/settings"
import { useBoolean, useProjectPermissions } from "@/composables"
import { LAB_OWNER_AND_MANAGER } from "@/composables/useLabPermissions"
import { useRouterPush } from "@/composables/useRouterPush"
import { deleteProtocol, getResearchEnvVariables, putProtocolInfo } from "@/service/api/project-protocols"
import { useAuthStore } from "@/store/modules/auth"
import { useClosableMessage, useLoading } from "@airalogy/composables"
import { getRealAiralogyId } from "@airalogy/shared"
import { $t } from "@airalogy/shared/locales"
import { copyToClip } from "@airalogy/shared/utils"
import { useOrProvideProjectInfoStore } from "./hooks/useProjectInfoStore"
import { useProtocolInfoStore } from "./hooks/useProtocolInfoStore"
import { licenseOptions } from "./modules/protocol/helpers/constatns"

defineOptions({ name: "EditProtocolSettings" })

const authStore = useAuthStore()
const { routerPushByKey } = useRouterPush()
const message = useClosableMessage()

interface FormModel extends BaseFormModel {
  name: string
  description?: string
  disciplines: string[]
  keywords: string[]
  license?: string
}

const { fetchProtocolInfoByUid, protocolInfo } = useProtocolInfoStore()! || {}
const { projectInfo } = useOrProvideProjectInfoStore(null)
const { canManageOwnProtocols, canManageOthersProtocols } = useProjectPermissions(projectInfo)
const route = useRoute()
const originalEnv = ref("")
const envDraft = ref("")
const showEnvValues = ref(false)
const isEnvEditing = ref(false)
const { bool: isEnvCopied, setTrue: setEnvCopied, setFalse: setEnvNotCopied } = useBoolean(false)
const { loading: envSaving, startLoading: startEnvSaving, endLoading: endEnvSaving } = useLoading()

const initValue = computed(
  (): FormModel => {
    if (!protocolInfo.value) {
      return {
        name: "",
        description: "",
        disciplines: [],
        keywords: [],
        license: "",
      }
    }

    const { name, description, disciplines, keywords } = protocolInfo.value

    return {
      name,
      description: description || "",
      disciplines: Array.isArray(disciplines) ? disciplines : disciplines ? String(disciplines).split(",").map(s => s.trim()) : [],
      keywords: Array.isArray(keywords) ? keywords : keywords ? String(keywords).split(",").map(s => s.trim()) : [],
      license: protocolInfo.value.metadata?.license || (protocolInfo.value as any).license || "",
    }
  },
)

const protocolIdDisplay = computed(() => {
  if (!protocolInfo.value)
    return ""

  return getRealAiralogyId(protocolInfo.value as any) || protocolInfo.value.uid || ""
})

const protocolVersionDisplay = computed(() => {
  if (!protocolInfo.value)
    return ""

  return `${protocolInfo.value.latest_version || protocolInfo.value.metadata?.version || ""}`
})

// Permission checks
const isProtocolOwner = computed(() => {
  if (!protocolInfo.value || !authStore.userInfo) {
    return false
  }
  return protocolInfo.value.user_id === authStore.userInfo.id
})

const isLabAdmin = computed(() => {
  const role = projectInfo.value?.user_lab_role
  return Boolean(role) && LAB_OWNER_AND_MANAGER.includes(role)
})

const canManageOwnProtocolsByRole = computed(() => {
  return canManageOwnProtocols.value || isLabAdmin.value
})

const canManageOthersProtocolsByRole = computed(() => {
  return canManageOthersProtocols.value || isLabAdmin.value
})

const isManagingOthersProtocol = computed(() => {
  if (!protocolInfo.value) {
    return false
  }
  return !isProtocolOwner.value && canManageOthersProtocolsByRole.value
})

const canManageProtocol = computed(() => {
  if (!protocolInfo.value || !authStore.userInfo) {
    return false
  }
  if (isProtocolOwner.value) {
    return canManageOwnProtocolsByRole.value || !projectInfo.value
  }
  return canManageOthersProtocolsByRole.value
})

const hasEditPermission = computed(() => canManageProtocol.value)
const hasDeletePermission = computed(() => canManageProtocol.value)
const deleteExtraWarning = computed(() => {
  return isManagingOthersProtocol.value
    ? $t("page.protocol.settings.adminDeleteNotice")
    : undefined
})

const hasEnvPermission = computed(() => canManageProtocol.value)

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
    if (!protocolInfo.value?.id) {
      throw new Error("Protocol ID is null")
    }

    const payload = {
      name: formData.name,
      description: formData.description,
      disciplines: formData.disciplines,
      keywords: formData.keywords,
      license: formData.license,
    }

    return await putProtocolInfo(protocolInfo.value.id, payload)
  },
  () => {
    // Refresh protocol info after successful update
    const { protocolUid, labUid, projectUid } = route.params as {
      protocolUid: string
      labUid: string
      projectUid: string
    }
    fetchProtocolInfoByUid({ labUid, projectUid, protocolUid })
  },
)

// Form validation rules
const rules = {
  ...getBaseRules($t("common.protocol")),
  name: [
    { required: true, message: $t("page.protocol.settings.validation.nameRequired") },
    { min: 1, max: 50, message: $t("page.protocol.settings.validation.nameLength") },
  ],
  description: [
    { max: 500, message: $t("page.protocol.settings.validation.descriptionLength") },
  ],
}

const hasEnvVars = computed(() => {
  return typeof envDraft.value === "string" && envDraft.value.trim().length > 0
})

const envVarsMask = computed(() => {
  if (!hasEnvVars.value)
    return ""

  const lines = (envDraft.value || "").toString().split("\n")
  return lines.map((line) => {
    const [key] = line.split("=")
    return key ? `${key}=${"*".repeat(8)}` : line
  }).join("\n")
})

const envDisplayValue = computed(() => {
  return hasEnvVars.value && !showEnvValues.value ? envVarsMask.value : envDraft.value
})

const envDirty = computed(() => envDraft.value !== originalEnv.value)

const envReadOnly = computed(() => {
  return !hasEnvPermission.value || !isEnvEditing.value || (hasEnvVars.value && !showEnvValues.value) || envSaving.value
})

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
    if (!protocolInfo.value?.id) {
      throw new Error("Protocol ID is null")
    }

    const result = await deleteProtocol(protocolInfo.value.id)
    return { data: result, error: result ? null : new Error("Delete failed") }
  },
  "Protocol",
  () => {
    const { lab, project } = protocolInfo.value || {}
    if (lab && project) {
      routerPushByKey("project-protocols", {
        params: {
          labUid: lab.uid,
          projectUid: project.uid,
        },
      })
    }
  },
)

// Handle environment variables input
function handleEnvInput(value: string) {
  if (hasEnvPermission.value && isEnvEditing.value) {
    envDraft.value = value
  }
}

// Handle copying environment variables
function handleCopyEnv() {
  if (!envDraft.value)
    return

  copyToClip(envDraft.value)
  message.success($t("page.protocol.settings.envCopied"))
  setEnvCopied()
  setTimeout(() => {
    setEnvNotCopied()
  }, 1000)
}

function startEnvEdit() {
  if (!hasEnvPermission.value) {
    return
  }
  isEnvEditing.value = true
}

function cancelEnvEdit() {
  envDraft.value = originalEnv.value || ""
  isEnvEditing.value = false
  showEnvValues.value = false
}

async function handleEnvSave() {
  if (!protocolInfo.value?.id || !hasEnvPermission.value || envSaving.value) {
    return
  }
  startEnvSaving()
  try {
    const { data, error } = await putProtocolInfo(protocolInfo.value.id, { env: envDraft.value })
    if (error) {
      message.error($t("page.protocol.settings.envSaveFailed"))
      return
    }
    if (data) {
      originalEnv.value = envDraft.value || ""
      isEnvEditing.value = false
      showEnvValues.value = false
      message.success($t("page.protocol.settings.envSaveSuccess"))
    }
  }
  catch {
    message.error($t("page.protocol.settings.envSaveFailed"))
  }
  finally {
    endEnvSaving()
  }
}

watch(() => protocolInfo.value?.id, async (id) => {
  if (id) {
    const { data, error } = await getResearchEnvVariables(id)
    if (data) {
      originalEnv.value = data.env_vars || ""
      envDraft.value = originalEnv.value
      isEnvEditing.value = false
      showEnvValues.value = false
    }
  }
}, { immediate: true })

// Load environment variables on mount
onMounted(async () => {
  const { protocolUid, labUid, projectUid } = route.params as {
    protocolUid: string
    labUid: string
    projectUid: string
  }
  await fetchProtocolInfoByUid({ labUid, projectUid, protocolUid })
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

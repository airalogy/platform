<template>
  <n-form v-if="totalEnvFiles > 0" :model="formModel" :rules="rules" size="medium">
    <n-alert type="info" class="mb-4">
      <template #icon>
        <n-icon><icon-tabler-info-circle /></n-icon>
      </template>
      <div>
        <p class="mb-2">
          <strong>{{ $t("page.hub.envEditor.handlingTitle") }}:</strong>
        </p>
        <ul class="list-disc list-inside text-sm space-y-1">
          <li>{{ $t("page.hub.envEditor.handlingItem1") }}</li>
          <li>{{ $t("page.hub.envEditor.handlingItem2") }}</li>
          <li>{{ $t("page.hub.envEditor.handlingItem3") }}</li>
          <li>{{ $t("page.hub.envEditor.handlingItem4") }}</li>
          <li>{{ $t("page.hub.envEditor.handlingItem5") }}</li>
          <li>{{ $t("page.hub.envEditor.handlingItem6") }}</li>
        </ul>
      </div>
    </n-alert>
    <n-collapse
      v-model:expanded-names="expandedNames"
      :theme-overrides="{ itemMargin: '8px 0 0 0', titlePadding: '8px 0 0 0' }"
      display-directive="show"
    >
      <!-- Summary Section -->
      <n-collapse-item :title="$t('page.hub.envEditor.summaryTitle')" name="summary" default-expanded>
        <template #header-extra>
          <n-tooltip trigger="hover">
            <template #trigger>
              <n-icon size="16" class="cursor-help text-gray-400">
                <icon-tabler-info-circle />
              </n-icon>
            </template>
            {{ $t("page.hub.envEditor.summaryTooltip") }}
          </n-tooltip>
        </template>

        <div class="grid grid-cols-1 mb-4 gap-4 md:grid-cols-3">
          <n-statistic :label="$t('page.hub.envEditor.totalFiles')" :value="totalEnvFiles" />
          <n-statistic :label="$t('page.hub.envEditor.filesToInclude')" :value="includedFilesCount" />
          <n-statistic :label="$t('page.hub.envEditor.filesToExclude')" :value="excludedFilesCount" />
        </div>
      </n-collapse-item>

      <!-- Environment Files -->
      <n-collapse-item
        v-if="props.showDetectedFiles && Object.keys(detectedEnvFiles).length > 0"
        :title="$t('page.hub.envEditor.filesTitle')"
        name="files"
        default-expanded
      >
        <template #header-extra>
          <n-badge :value="Object.keys(detectedEnvFiles).length" type="success">
            <n-tooltip trigger="hover">
              <template #trigger>
                <n-icon size="16" class="cursor-help text-gray-400">
                  <icon-tabler-info-circle />
                </n-icon>
              </template>
              {{ $t("page.hub.envEditor.filesTooltip") }}
            </n-tooltip>
          </n-badge>
        </template>

        <div class="space-y-4">
          <div
            v-for="(content, fileName) in detectedEnvFiles"
            :key="`detected-${fileName}`"
            class="border rounded-lg bg-blue-50 p-4"
          >
            <n-form-item :path="`detectedFiles.${fileName}.include`" :show-label="false">
              <div class="w-full">
                <div class="mb-3 flex items-center justify-between">
                  <div class="flex items-center gap-3">
                    <n-checkbox
                      :disabled="fileName === '.env' || fileName.endsWith('/.env')"
                      :checked="envFileInclusion[fileName] || false"
                      @update:checked="(checked: boolean) => toggleEnvFileInclusion(fileName, checked)"
                    >
                      <span class="text-sm font-medium">{{ fileName }}</span>
                    </n-checkbox>
                    <n-tag size="small" type="info">
                      {{ formatFileSize(getContentSize(content)) }}
                    </n-tag>
                  </div>
                  <div class="flex gap-2">
                    <n-button
                      v-if="props.allowDetectedFileEditing && editingEnvFile !== fileName"
                      size="small"
                      type="primary"
                      ghost
                      @click="startEditingEnvFile(fileName, editedContents[fileName] || content)"
                    >
                      <template #icon>
                        <n-icon><icon-tabler-edit /></n-icon>
                      </template>
                      {{ $t("common.edit") }}
                    </n-button>
                    <template v-else-if="props.allowDetectedFileEditing">
                      <n-button size="small" type="primary" @click="saveEnvFileEdit">
                        <template #icon>
                          <n-icon><icon-tabler-check /></n-icon>
                        </template>
                        {{ $t("common.save") }}
                      </n-button>
                      <n-button size="small" @click="cancelEnvFileEdit">
                        <template #icon>
                          <n-icon><icon-tabler-x /></n-icon>
                        </template>
                        {{ $t("common.cancel") }}
                      </n-button>
                    </template>

                    <n-popconfirm v-if="editingEnvFile !== fileName" @positive-click="emit('remove', fileName)" @click.stop>
                      <template #trigger>
                        <n-button
                          size="small"
                          type="error"
                          quaternary
                        >
                          <template #icon>
                            <n-icon><icon-tabler-trash /></n-icon>
                          </template>
                          {{ $t("common.remove") }}
                        </n-button>
                      </template>
                      {{ $t("page.hub.envEditor.removeConfirm") }}
                    </n-popconfirm>
                  </div>
                </div>

                <!-- Content display/edit -->
                <n-form-item v-if="editingEnvFile === fileName" :show-label="false">
                  <n-input
                    v-model:value="editedEnvContent"
                    type="textarea"
                    :rows="8"
                    :placeholder="$t('page.hub.envEditor.contentPlaceholder')"
                    class="text-xs font-mono"
                  />
                </n-form-item>
                <div v-else class="max-h-40 overflow-y-auto border rounded bg-white p-3 text-xs font-mono">
                  <pre class="whitespace-pre-wrap">{{ editedContents[fileName] || content }}</pre>
                </div>

                <!-- Inclusion status -->
                <div class="mt-2 flex items-center justify-between">
                  <n-tag :type="envFileInclusion[fileName] ? 'success' : 'warning'" size="tiny">
                    {{ envFileInclusion[fileName] ? $t("page.hub.envEditor.includeLabel") : $t("page.hub.envEditor.excludeLabel") }}
                  </n-tag>
                  <!-- <span v-if="props.detectedEnvFiles['.env']" class="text-xs text-gray-500">Detected from package</span> -->
                </div>
              </div>
            </n-form-item>
          </div>
        </div>
      </n-collapse-item>
    </n-collapse>
  </n-form>
</template>

<script setup lang="ts">
import type { UploadFileInfo } from "naive-ui"
import { $t } from "@airalogy/shared/locales"
import IconTablerCheck from "~icons/tabler/check"
import IconTablerEdit from "~icons/tabler/edit"
import IconTablerInfoCircle from "~icons/tabler/info-circle"
import IconTablerX from "~icons/tabler/x"

interface Props {
  detectedEnvFiles: Record<string, string>
  uploadedEnvFiles: UploadFileInfo[]
  uploadedEnvContents: Record<string, string>
  showDetectedFiles?: boolean
  showUploadedFiles?: boolean
  allowDetectedFileEditing?: boolean
  allowUploadedFileEditing?: boolean
  defaultInclusionState?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showDetectedFiles: true,
  showUploadedFiles: true,
  allowDetectedFileEditing: true,
  allowUploadedFileEditing: true,
  defaultInclusionState: false,
})

const emit = defineEmits<{
  (e: "update:inclusion", value: Record<string, boolean>): void
  (e: "remove", name: string): void
  (e: "update:edited-contents", value: Record<string, string>): void
}>()

// State for environment file editing and selection
const editingEnvFile = ref<string | null>(null)
const editedEnvContent = ref<string>("")
const envFileInclusion = ref<Record<string, boolean>>({})
const editedContents = ref<Record<string, string>>({})
const expandedNames = ref<string[]>(["summary", "files"])

// Form model and rules
const formModel = ref({})
const rules = ref({})
const totalEnvFiles = computed(() => Object.keys(props.detectedEnvFiles).length)

const includedFilesCount = computed(() =>
  Object.values(envFileInclusion.value).filter(Boolean).length,
)

const excludedFilesCount = computed(() =>
  totalEnvFiles.value - includedFilesCount.value,
)

// Utility functions
function formatFileSize(bytes: number): string {
  if (bytes === 0)
    return "0 B"
  const k = 1024
  const sizes = ["B", "KB", "MB", "GB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${Number.parseFloat((bytes / (k ** i)).toFixed(1))} ${sizes[i]}`
}

function getContentSize(content: string): number {
  return new Blob([content]).size
}

// Environment file editing functions
function startEditingEnvFile(fileName: string, content: string) {
  editingEnvFile.value = fileName
  editedEnvContent.value = content
}

function saveEnvFileEdit() {
  if (editingEnvFile.value) {
    const fileName = editingEnvFile.value
    editedContents.value[fileName] = editedEnvContent.value
    emit("update:edited-contents", { ...editedContents.value })
    cancelEnvFileEdit()
  }
}

function cancelEnvFileEdit() {
  editingEnvFile.value = null
  editedEnvContent.value = ""
}

function toggleEnvFileInclusion(fileName: string, include: boolean) {
  // TODO: need server implement
  envFileInclusion.value[fileName] = (fileName !== ".env" && !fileName.endsWith("/.env")) && include
  emit("update:inclusion", { ...envFileInclusion.value })
}

// Initialize inclusion state when files are detected or uploaded
watch([() => props.detectedEnvFiles, () => props.uploadedEnvFiles], () => {
  // Set default inclusion state for detected files
  if (props.showDetectedFiles) {
    Object.keys(props.detectedEnvFiles).forEach((fileName) => {
      if (!(fileName in envFileInclusion.value)) {
        envFileInclusion.value[fileName] = props.defaultInclusionState
      }
      delete editedContents.value[fileName]
    })
  }

  // Set default inclusion state for uploaded files
  if (props.showUploadedFiles) {
    props.uploadedEnvFiles.forEach((file) => {
      if (file.name && !(file.name in envFileInclusion.value)) {
        envFileInclusion.value[file.name] = props.defaultInclusionState
      }
    })
  }

  emit("update:inclusion", { ...envFileInclusion.value })
}, { deep: true, immediate: true })
</script>

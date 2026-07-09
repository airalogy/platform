<template>
  <n-button v-if="props.showButton" v-bind="props.buttonProps" secondary @click.stop="open">
    <template v-if="props.showIcon" #icon>
      <icon-tabler-file-import />
    </template>
    <span v-if="props.showTrigger">
      {{ props.trigger || t("page.protocol.airaImport.trigger") }}
    </span>
  </n-button>

  <n-modal
    v-model:show="showModal"
    preset="card"
    :title="t('page.protocol.airaImport.title')"
    class="w-[calc(100vw-32px)] max-w-[620px]"
    :mask-closable="!loading"
    @after-leave="resetState"
  >
    <div class="space-y-4">
      <project-selector
        target="project"
        :default-lab="defaultLab"
        :default-project="defaultProject"
        :disable-default="Boolean(defaultProject)"
        :cascader-props="{ placeholder: t('page.protocol.airaImport.projectPlaceholder') }"
        @update:project="selectedProject = $event"
      />

      <n-upload
        :file-list="fileList"
        :default-upload="false"
        :max="1"
        accept=".aira"
        @before-upload="handleBeforeUpload"
        @update:file-list="handleFileListUpdate"
      >
        <n-upload-dragger>
          <div class="flex flex-col items-center gap-2 py-5">
            <n-icon size="34" class="text-primary">
              <icon-local-cloud-upload />
            </n-icon>
            <div class="text-sm font-medium">
              {{ t("page.protocol.airaImport.dropText") }}
            </div>
            <div class="max-w-[420px] text-center text-xs text-gray-500 leading-5">
              {{ t("page.protocol.airaImport.supportHint") }}
            </div>
          </div>
        </n-upload-dragger>
      </n-upload>

      <n-alert
        v-if="errorMessage"
        type="error"
        :title="t('page.protocol.airaImport.errorTitle')"
      >
        <div class="whitespace-pre-wrap text-xs leading-5">
          {{ errorMessage }}
        </div>
      </n-alert>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button :disabled="loading" @click="showModal = false">
          {{ t("common.cancel") }}
        </n-button>
        <n-button
          type="primary"
          :disabled="!selectedProject?.id || !getSelectedFile()"
          :loading="loading"
          @click="handleImport"
        >
          {{ t("page.protocol.airaImport.submit") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { Lab, Project } from "@/components/apply-steps/project-selector.vue"
import type { ImportAiraArchiveResponse } from "@/service/api/project-protocols"
import type { ButtonProps, UploadFileInfo } from "naive-ui"
import ProjectSelector from "@/components/apply-steps/project-selector.vue"
import { postImportAiraArchive } from "@/service/api/project-protocols"
import { useClosableMessage } from "@airalogy/composables"
import { useI18n } from "vue-i18n"

defineOptions({ name: "ImportAiraArchiveModal" })

const props = withDefaults(defineProps<{
  project?: Api.Project.MyProjectInfo | null
  showButton?: boolean
  showIcon?: boolean
  showTrigger?: boolean
  trigger?: string
  buttonProps?: ButtonProps & { class?: string }
}>(), {
  project: null,
  showButton: true,
  showIcon: true,
  showTrigger: true,
  trigger: "",
  buttonProps: () => ({}),
})

const emit = defineEmits<{
  (e: "imported", result: ImportAiraArchiveResponse): void
}>()

const message = useClosableMessage()
const { t } = useI18n()

const showModal = ref(false)
const loading = ref(false)
const fileList = ref<UploadFileInfo[]>([])
const selectedProject = ref<Project | null>(null)
const errorMessage = ref("")

function open() {
  showModal.value = true
}

const defaultLab = computed<Lab | null>(() => {
  const project = props.project
  if (!project?.lab_id || !project.lab_uid) {
    return null
  }
  return {
    id: project.lab_id,
    uid: project.lab_uid,
    name: project.lab_name || project.group_name || project.lab_uid,
  }
})

const defaultProject = computed<Project | null>(() => {
  const project = props.project
  if (!project?.id || !project.uid) {
    return null
  }
  return {
    id: project.id,
    uid: project.uid,
    name: project.name,
  }
})

watch(
  [defaultLab, defaultProject],
  ([, project]) => {
    selectedProject.value = project
  },
  { immediate: true },
)

function resetState() {
  fileList.value = []
  errorMessage.value = ""
  loading.value = false
  selectedProject.value = defaultProject.value
}

function handleBeforeUpload(options: { file: UploadFileInfo }) {
  const filename = options.file.name || ""
  if (!filename.toLowerCase().endsWith(".aira")) {
    message.error(t("page.protocol.airaImport.airaOnly"))
    return false
  }
  return true
}

function handleFileListUpdate(nextFileList: UploadFileInfo[]) {
  fileList.value = nextFileList.slice(-1)
  errorMessage.value = ""
}

function getSelectedFile() {
  return fileList.value[0]?.file || null
}

function getErrorDetail(error: unknown) {
  return (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
}

function parseErrorMessage(error: unknown) {
  const detail = getErrorDetail(error)
  if (typeof detail === "string") {
    return detail
  }
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown }).message
    const errors = (detail as { errors?: unknown }).errors
    if (Array.isArray(errors) && errors.length > 0) {
      return errors.map(item => String(item)).join("\n")
    }
    if (typeof message === "string") {
      return message
    }
  }
  if (error instanceof Error) {
    return error.message
  }
  return t("page.protocol.airaImport.unknownError")
}

async function handleImport() {
  const projectId = selectedProject.value?.id
  const file = getSelectedFile()
  if (!projectId) {
    message.warning(t("page.protocol.airaImport.projectRequired"))
    return
  }
  if (!file) {
    message.warning(t("page.protocol.airaImport.fileRequired"))
    return
  }

  loading.value = true
  errorMessage.value = ""
  try {
    const result = await postImportAiraArchive(projectId, { file })
    message.success(t("page.protocol.airaImport.success", {
      protocols: result.protocols.length,
      records: result.imported_record_count,
      files: result.imported_file_count,
    }))
    emit("imported", result)
    showModal.value = false
  }
  catch (error) {
    errorMessage.value = parseErrorMessage(error)
  }
  finally {
    loading.value = false
  }
}

defineExpose({ open })
</script>

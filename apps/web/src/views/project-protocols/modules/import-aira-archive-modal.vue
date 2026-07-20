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
    class="max-w-[620px] w-[calc(100vw-32px)]"
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
        v-if="errorInfo"
        type="error"
        :title="t('page.protocol.airaImport.errorTitle')"
      >
        <div class="break-words text-sm leading-6">
          {{ errorInfo.message }}
        </div>
        <ul v-if="errorInfo.details.length" class="mt-2 list-disc break-words pl-5 text-xs leading-5 space-y-1">
          <li v-for="(detail, index) in errorInfo.details" :key="`${index}-${detail}`">
            {{ detail }}
          </li>
        </ul>
        <div
          v-if="errorInfo.status || errorInfo.requestId"
          class="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-red-200 pt-2 text-xs text-gray-600"
        >
          <span v-if="errorInfo.status">
            {{ t("page.protocol.airaImport.httpStatus", { status: errorInfo.status }) }}
          </span>
          <span v-if="errorInfo.requestId" class="break-all">
            {{ t("page.protocol.airaImport.requestId", { id: errorInfo.requestId }) }}
          </span>
        </div>
        <div v-if="errorInfo.requestId" class="mt-2 text-xs text-gray-500 leading-5">
          {{ t("page.protocol.airaImport.requestIdHint") }}
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

interface ImportErrorInfo {
  message: string
  details: string[]
  status?: number
  requestId?: string
}

const errorInfo = ref<ImportErrorInfo | null>(null)

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
  errorInfo.value = null
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
  errorInfo.value = null
}

function getSelectedFile() {
  return fileList.value[0]?.file || null
}

function errorDetailText(value: unknown): string | null {
  if (typeof value === "string") {
    return value
  }
  if (!value || typeof value !== "object") {
    return null
  }

  const item = value as Record<string, unknown>
  const message = [item.message, item.msg, item.detail].find(candidate => typeof candidate === "string")
  const namedLocation = [item.record_path, item.path, item.field].find(candidate => typeof candidate === "string")
  const location = typeof namedLocation === "string"
    ? namedLocation
    : Array.isArray(item.loc)
      ? item.loc.map(String).join(" > ")
      : null
  if (typeof message === "string") {
    return typeof location === "string" ? `${location}: ${message}` : message
  }
  if (location) {
    return location
  }

  try {
    return JSON.stringify(value)
  }
  catch {
    return String(value)
  }
}

function responseHeader(headers: unknown, name: string): string | undefined {
  if (!headers || typeof headers !== "object") {
    return undefined
  }
  const headerBag = headers as Record<string, unknown> & { get?: (key: string) => unknown }
  const fromGetter = typeof headerBag.get === "function" ? headerBag.get(name) : undefined
  const value = fromGetter ?? headerBag[name] ?? headerBag[name.toLowerCase()]
  return typeof value === "string" && value ? value : undefined
}

function parseErrorInfo(error: unknown): ImportErrorInfo {
  const response = (error as {
    response?: {
      status?: number
      data?: unknown
      headers?: unknown
    }
  })?.response
  const responseData = response?.data
  const detail = responseData && typeof responseData === "object" && "detail" in responseData
    ? (responseData as { detail?: unknown }).detail
    : responseData
  const details: string[] = []
  let messageText = ""
  let code = ""
  let requestId = responseHeader(response?.headers, "x-request-id")

  if (typeof detail === "string") {
    if (detail !== "Internal Server Error") {
      messageText = detail
    }
  }
  if (Array.isArray(detail)) {
    details.push(
      ...detail
        .map(errorDetailText)
        .filter((item): item is string => Boolean(item)),
    )
  }
  else if (detail && typeof detail === "object") {
    const detailObject = detail as Record<string, unknown>
    code = typeof detailObject.code === "string" ? detailObject.code : ""
    messageText = typeof detailObject.message === "string" ? detailObject.message : ""
    requestId = typeof detailObject.request_id === "string"
      ? detailObject.request_id
      : requestId
    const errors = detailObject.errors
    if (Array.isArray(errors) && errors.length > 0) {
      details.push(
        ...errors
          .map(errorDetailText)
          .filter((item): item is string => Boolean(item)),
      )
    }
    if (typeof detailObject.record_path === "string") {
      details.unshift(t("page.protocol.airaImport.recordPath", {
        path: detailObject.record_path,
      }))
    }
  }

  const status = response?.status
  if (code === "storage_unavailable") {
    messageText = t("page.protocol.airaImport.storageUnavailable")
  }
  else if (status && status >= 500) {
    messageText = t("page.protocol.airaImport.serverError")
  }
  else if (!response) {
    messageText = t("page.protocol.airaImport.networkError")
  }
  else if (!messageText && error instanceof Error && !error.message.startsWith("Request failed with status code")) {
    messageText = error.message
  }

  return {
    message: messageText || t("page.protocol.airaImport.unknownError"),
    details,
    status,
    requestId,
  }
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
  errorInfo.value = null
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
    errorInfo.value = parseErrorInfo(error)
  }
  finally {
    loading.value = false
  }
}

defineExpose({ open })
</script>

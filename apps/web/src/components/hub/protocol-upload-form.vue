<template>
  <n-form ref="formRef" :model="model" :rules="rules" size="large">
    <step-header
      :step="1"
      :title="$t('page.hub.protocolUpload.stepApplyToProject')"
    >
      <n-form-item :show-label="false" path="projectId" required :show-feedback="false">
        <project-selector
          class="p-3"
          :protocol-info="props.protocolInfo"
          target="project"
          :default-project="defaultProject"
          :default-lab="defaultLab"
          :disable-default="props.disableDefault"
          @update:lab="handleTargetLabUpdate"
          @update:project="handleTargetProjectUpdate"
        />
      </n-form-item>
    </step-header>
    <step-header
      v-if="!props.skipUpload"
      :step="2"
      :title="$t('page.hub.protocolUpload.stepSelectPackage')"
    >
      <n-form-item :show-label="false" path="file" required class="mt-3 px-3">
        <zip-file-preview
          ref="filePreviewRef"
          v-model:file="uploadedFile"
          v-model:file-content="fileContent"
          :accepted-file-types="acceptedFileTypes"
          :max-file-size="10"
          show-reset
          @selected:file="handleFileSelected"
          @loaded:content="handleContentLoaded"
        >
          <template #upload-text>
            <p class="text-base">
              {{ props.uploadType === "upload-zip"
                ? $t("page.hub.protocolUpload.uploadInstructionZip")
                : $t("page.hub.protocolUpload.uploadInstructionFile") }}
            </p>
            <p class="text-sm text-gray-500">
              {{ $t("page.hub.protocolUpload.uploadSupportTypes", { types: acceptedFileTypes }) }}
            </p>
          </template>
        </zip-file-preview>
      </n-form-item>
    </step-header>
    <step-header
      :step="props.skipUpload ? 2 : 3"
      :title="$t('page.hub.protocolUpload.stepConfigureProtocol')"
    >
      <div class="px-3">
        <protocol-details
          v-if="props.skipUpload || model.fileList.length > 0"
          v-model:metadata="model.metadata"
          :show-label="false"
          :show-metadata="props.skipUpload || model.fileList.length > 0"
          :original-toml="protocolData?.toml_config || ''"
          :check-loading="checkLoading"
          :check-id="checkId"
          :aimd-content="protocolData?.protocol"
          :lab-uid="props.projectInfo?.lab_uid || props.labUid || targetLab?.uid"
          :project-uid="props.projectInfo?.uid || props.projectUid || targetProject?.uid"
          :skip-upload="props.skipUpload"
          :should-check-duplicate="shouldCheckDuplicate"
          :disable-default="props.disableDefault"
        />
        <n-empty v-else :description="$t('page.hub.protocolUpload.emptySelectPackage')" :show-icon="false" />
      </div>
    </step-header>
    <step-header
      :step="props.skipUpload ? 3 : 4"
      :title="$t('page.hub.protocolUpload.stepEnvConfig')"
    >
      <div v-if="props.skipUpload || model.fileList.length > 0" class="p-3">
        <env-editor
          :detected-env-files="filePreviewRef?.envFiles || {}"
          :uploaded-env-files="envFiles"
          :uploaded-env-contents="envFileContents"
          @remove="handleRemoveFileAndContent"
          @update:inclusion="handleEnvInclusionUpdate"
          @update:edited-contents="handleEnvEditedContentsUpdate"
        />

        <n-button v-if="!hasEnvFile" type="primary" class="mt-3 w-full" @click="handleAddEnvFile">
          {{ $t("page.hub.protocolUpload.addEnvFile") }}
        </n-button>
        <n-divider>{{ $t("common.or") }}</n-divider>
        <n-form-item :show-label="false" path="envFiles" class="mb-4">
          <n-upload
            v-model:file-list="envFiles"
            :show-download-button="false"
            :show-remove-button="true"
            list-type="text"
            accept=".env,.env.local,.env.development,.env.production,.env.staging,.env.example"
            :show-file-list="false"
            @before-upload="handleEnvFileBeforeUpload"
          >
            <n-upload-dragger class="upload-area flex flex-col items-center justify-center p-6">
              <n-icon size="40" class="mb-2 text-gray-400">
                <icon-tabler-file-settings />
              </n-icon>
              <p class="mb-1 text-base">
                {{ $t("page.hub.protocolUpload.uploadEnvTitle") }}
              </p>
              <p class="text-sm text-gray-500">
                {{ $t("page.hub.protocolUpload.uploadEnvHint") }}
              </p>
            </n-upload-dragger>
          </n-upload>
        </n-form-item>
      </div>
      <n-empty v-else :description="$t('page.hub.protocolUpload.emptySelectPackage')" :show-icon="false" />
    </step-header>
    <slot name="extra-fields" />
  </n-form>
</template>

<script setup lang="tsx">
import type { ProtocolData } from "@/constants/protocol"
import type { UploadContent } from "@airalogy/components/src/monaco-editor/types/upload"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { ValidateError } from "async-validator"
import type { ApplyOption, FormModel, UploadModel } from "../apply-steps/composables/useApplyProtocolState"
import type { Lab, Project } from "../apply-steps/project-selector.vue"
import { createUidValidator, createVersionValidator, useFormRules, useLoading } from "@/composables"
import { protocolParsingEventBus } from "@/composables/useProtocolParsingEventBus"
import { postCheckProtocolIdDuplicate } from "@/service/api/protocol"
import { useOrProvideProtocolEditorContext } from "@/views/editor/composables/useProtocolEditorContext"
import ZipFilePreview from "@airalogy/components/file-preview/zip-file-preview.vue"
import { useClosableMessage } from "@airalogy/composables"
import { ENV_EXTENSIONS, type ZipItem } from "@airalogy/shared/utils"
import { formatPydanticError } from "@airalogy/shared/utils/errorFormatter.js"
import { useVModel } from "@vueuse/core"
import IconTablerFileSettings from "~icons/tabler/file-settings"
import { type FormInst, type UploadFileInfo, useDialog } from "naive-ui"
import { nanoid } from "nanoid"
import { computed, provide, ref, watch } from "vue"
import { $t } from "../../locales"
import ProtocolDetails from "../apply-steps/protocol-details.vue"
import EnvEditor from "./env-editor.vue"

interface IProps {
  uploadType: Omit<ApplyOption, "existing">
  protocolData?: ProtocolData | null
  model: UploadModel
  checkId?: boolean
  projectInfo?: Api.Project.MyProjectInfo | null
  labUid?: string | null
  projectUid?: string | null
  protocolInfo?: ProtocolModels.ProjectProtocolInfo | null
  skipUpload?: boolean
  disableDefault?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  checkId: true,
  projectInfo: undefined,
  labUid: undefined,
  projectUid: undefined,
  protocolInfo: undefined,
  skipUpload: false,
  disableDefault: true,
})

const emit = defineEmits<{
  (e: "update:model", value: UploadModel): void
  (e: "update:version", value: string): void
  (e: "loaded:content", content: UploadContent): void
  (e: "update:form-ref", value: FormInst | null): void
  (e: "update:target-lab", value: Lab | null): void
  (e: "update:target-project", value: Project | null): void
  (e: "remove", path: string): void
}>()

interface DirectoryFile {
  name: string
  path: string
  file: File
  size?: number
  lastModified?: number
}

interface DirectoryUpload {
  type: "directory"
  files: DirectoryFile[]
}

export interface ZipUpload {
  type: "zip"
  content: {
    items: ZipItem[]
    root: string
  }
}

const { defaultRequiredRule } = useFormRules()
const versionValidator = createVersionValidator()

const formRef = ref<FormInst | null>(null)
const model = useVModel(props, "model", emit)
const { loading: checkLoading, startLoading: startCheckLoading, endLoading: endCheckLoading } = useLoading()
const zipContent = ref<{ items: ZipItem[], root: string } | null>(null)

provide("protocol-form-ref", formRef)

const message = useClosableMessage()
const acceptedFileTypes = computed(() =>
  props.uploadType === "upload-zip" ? ".zip" : ".json,.yaml,.yml",
)
type MetadataKeys = `metadata.${keyof ProtocolModels.ProtocolMetaData}`
const targetLab = ref<Lab | null>(null)
const targetProject = ref<Project | null>(null)

// Try to get editor context (will be available when used in editor)
let editorContext: ReturnType<typeof useOrProvideProtocolEditorContext> | null = null
try {
  editorContext = useOrProvideProtocolEditorContext()
}
catch {
  // Not in editor context, that's fine
}

const defaultProject = computed(() => {
  if (props.protocolInfo?.project) {
    return props.protocolInfo.project
  }
  if (props.projectInfo) {
    return props.projectInfo
  }
  // Use project info from editor context
  if (editorContext?.projectInfo.value) {
    return editorContext.projectInfo.value
  }
  return null
})

const defaultLab = computed(() => {
  const { protocolInfo, projectInfo } = props
  if (protocolInfo?.lab) {
    return protocolInfo.lab
  }
  if (projectInfo) {
    const { lab_uid, lab_name, lab_id } = projectInfo
    if (lab_uid) {
      return {
        uid: lab_uid,
        name: lab_name,
        id: lab_id,
      }
    }
  }
  // Use lab info from editor context
  if (editorContext?.projectInfo.value) {
    const { lab_uid, lab_name, lab_id } = editorContext.projectInfo.value
    if (lab_uid) {
      return {
        uid: lab_uid,
        name: lab_name,
        id: lab_id,
      }
    }
  }
  return null
})

// Watch editor context and pre-fill model when ready
if (editorContext) {
  watch(
    () => editorContext.isReady.value && editorContext.projectInfo.value,
    (projectInfo) => {
      if (projectInfo) {
        const { labUid, projectUid, projectId } = editorContext
        if (!model.value.labUid) {
          model.value.labUid = labUid.value
        }
        if (!model.value.projectUid) {
          model.value.projectUid = projectUid.value
        }
        if (!model.value.projectId) {
          model.value.projectId = projectId.value
        }
      }
    },
    { immediate: true },
  )
}

const shouldCheckDuplicate = computed(() => {
  if (!props.protocolInfo) {
    return true
  }

  const { project } = props.protocolInfo

  return targetProject.value && targetProject.value.id !== project.id
})

function handleTargetLabUpdate(lab: Lab | null) {
  targetLab.value = lab
  model.value.labUid = lab?.uid || null
  emit("update:target-lab", lab)
}

function handleTargetProjectUpdate(project: Project | null) {
  targetProject.value = project
  model.value.projectUid = project?.uid || null
  model.value.projectId = project?.id || null

  const targetProjectRef = formRef.value?.formItems?.targetProjectId?.[0]
  if (targetProjectRef) {
    targetProjectRef.restoreValidation()
  }

  emit("update:target-project", project)
}

const rules: Partial<Record<Exclude<keyof FormModel, "metadata"> | MetadataKeys | "name" | "fileList" | "projectId", App.Global.FormRule[]>> = {
  "name": [defaultRequiredRule],
  "version": versionValidator,
  "fileList": [
    {
      required: true,
      validator: (_: any, val: any) => Array.isArray(val) && val.length > 0,
      message: $t("form.file.required"),
    },
  ],
  "protocolId": [defaultRequiredRule],
  "projectId": [defaultRequiredRule],
  "metadata.version": [defaultRequiredRule],
  "metadata.name": [defaultRequiredRule],
  "metadata.authors": [],
  "metadata.maintainers": [],
  "metadata.id": [defaultRequiredRule, ...createUidValidator({ fieldName: $t("page.protocol.apply.setupForm.protocolIdLabel") })],
  "metadata.airalogy_protocol_id": [defaultRequiredRule, {
    key: "check-airalogy-protocol-id",
    asyncValidator: async (rule) => {
      const { labUid, projectUid, projectInfo } = props
      if (!props.checkId) {
        return
      }

      const { renderMessageKey } = rule
      const { id, version } = model.value.metadata
      // const { labUid, projectUid } = route.params as { labUid: string, projectUid: string }
      const targetLabUid = labUid || projectInfo?.lab_uid || targetLab.value?.uid
      const targetProjectUid = projectUid || projectInfo?.uid || targetProject.value?.uid
      if (!id || !version || !targetLabUid || !targetProjectUid) {
        throw new Error($t("page.hub.protocolUpload.labProjectRequired"))
      }

      startCheckLoading()
      const { data, error } = await postCheckProtocolIdDuplicate({ uid: id, version, labUid: targetLabUid, projectUid: targetProjectUid })
      endCheckLoading()

      if (error) {
        const data = error.response?.data as any
        if (data?.detail) {
          throw data.detail
        }
        else {
          const errorMessage = formatPydanticError(data, {})
          throw errorMessage
        }
      }
      if (!data.valid) {
        // eslint-disable-next-line no-throw-literal
        throw { ...data, renderMessageKey }
      }

      message.success($t("page.protocol.apply.setupForm.protocolIdValid"))
    },
    renderMessage: (error) => {
      const { message, suggested_version } = error as (ValidateError & { suggested_version: string })
      if (suggested_version) {
        return (
          <div>
            <span>
              {message}
              .
            </span>
            <span class="ml-1">
              {$t("page.hub.protocolUpload.changeVersion")}
              <span class="mx-1 underline">
                {suggested_version}
              </span>
              ?
            </span>
            <tooltip-button
              onClick={() => handleUpdateVersion(suggested_version)}
              tooltip={$t("page.hub.protocolUpload.updateVersionTooltip")}
              button-props={{
                type: "primary",
                size: "small",
                class: "ml-2",
              }}
            >
              {$t("common.accept")}
            </tooltip-button>
          </div>
        )
      }

      return message
    },
  }],
}

const uploadedFile = ref<File | null>(null)
const fileContent = ref<Record<string, string> | null>(null)
const filePreviewRef = ref<InstanceType<typeof ZipFilePreview> | null>(null)

// Environment file handling
const envFiles = ref<UploadFileInfo[]>([])

// State for environment file editing and selection
const envFileInclusion = ref<Record<string, boolean>>({})

// Computed property to get environment files from file-preview content
// const detectedEnvFiles = computed(() => {
//   const envData: Record<string, string> = {}

//   // Get env content from file-preview component if available
//   if (filePreviewRef.value?.envFileContent) {
//     envData[".env"] = filePreviewRef.value.envFileContent
//   }

//   if (filePreviewRef.value?.envExampleContent) {
//     envData[".env.example"] = filePreviewRef.value.envExampleContent
//   }

//   return envData
// })

function handleAddEnvFile() {
  if (!filePreviewRef.value || (".env" in filePreviewRef.value.envFiles)) {
    return
  }

  filePreviewRef.value.envFiles[".env"] = "ENV_VAR="
}

// Get files to exclude from package (unchecked files)
const unsubscribe = protocolParsingEventBus.on(async (error) => {
  const { line, fileName } = error
  if (line && filePreviewRef.value) {
    await filePreviewRef.value.openPreview(fileName)
    filePreviewRef.value.highlightLine(line)
  }
})

function handleFileSelected(file: File | null) {
  try {
    if (!file) {
      model.value.fileList = []
      return
    }

    model.value.fileList = [{
      id: nanoid(),
      name: file.name,
      status: "finished",
      file,
    }]
  }
  catch (error) {
    const err = error as Error
    protocolParsingEventBus.emit({
      message: err.message,
      fileName: file?.name,
    })
  }
}

function handleContentLoaded(content: UploadContent | null) {
  if (props.uploadType !== "upload-zip" || !content) {
    return
  }

  try {
    const targetProjectRef = formRef.value?.formItems?.projectId?.[0]
    if (targetProjectRef) {
      targetProjectRef.validate().catch((err) => {
        console.error(err)
        message.warning($t("page.hub.protocolUpload.projectRequired"))
      })
    }

    if (content.type === "zip") {
      zipContent.value = content.content
    }

    emit("loaded:content", content)
  }
  catch (error) {
    const err = error as Error
    const lineMatch = err.message.match(/at line (\d+)/)
    const lineNumber = lineMatch ? Number.parseInt(lineMatch[1]) : undefined

    protocolParsingEventBus.emit({
      message: err.message,
      line: lineNumber,
      fileName: uploadedFile.value?.name,
    })
  }
}

function handleUpdateVersion(version: string) {
  model.value.metadata.version = version
  message.success(`Updated to version ${version}`)
  if (formRef.value) {
    formRef.value.restoreValidation()
  }
}

const uploadEnvFiles = ref<string[]>([])
const envFileContents = ref<Record<string, string>>({})
const dialog = useDialog()
// Validate file type
async function handleEnvFileBeforeUpload(data: { file: UploadFileInfo, fileList: UploadFileInfo[] }): Promise<boolean> {
  const { file: fileInfo } = data
  const { file, name, id } = fileInfo

  const isValidType = ENV_EXTENSIONS.some(ext => name?.endsWith(ext))
  const fullName = zipContent.value?.root ? `${zipContent.value.root}${name}` : name

  if (!isValidType) {
    message.error($t("page.hub.protocolUpload.envFilesOnly"))
    return false
  }

  // Read file content for preview
  if (file) {
    try {
      const content = await file.text()
      if (filePreviewRef.value?.envFiles) {
        if (filePreviewRef.value.envFiles[fullName]) {
          await new Promise((res, rej) => dialog.warning({
            title: $t("page.hub.protocolUpload.fileExistsTitle", { name }),
            content: $t("page.hub.protocolUpload.overrideConfirm"),
            positiveText: $t("common.confirm"),
            negativeText: $t("common.cancel"),
            onPositiveClick() { res(true) },
            onNegativeClick() { rej("cancel") },
            onMaskClick() {
              rej("cancel")
            },
          }),
          )

          // @ts-expect-error it !== data
          const targetIndex = envFiles.value.findIndex(it => it !== data && it.name === name)
          if (targetIndex !== -1) {
            const target = envFiles.value.splice(targetIndex, 1)
            // envFileContents.value[id]
            if (target[0]?.id) {
              delete envFileContents.value[target[0].id]
            }
          }
        }

        filePreviewRef.value.envFiles[fullName] = content
      }
      else if (filePreviewRef.value) {
        filePreviewRef.value.envFiles = { [fullName]: content }
      }

      envFileContents.value[id] = content
      uploadEnvFiles.value.push(fullName)
    }
    catch (error) {
      console.error("Error reading env file:", error)
    }
  }

  return true
}

function handleRemoveFileAndContent(name: string) {
  if (name && filePreviewRef.value?.envFiles?.[name as string]) {
    delete filePreviewRef.value.envFiles[name as string]
  }
  const targetFileIndex = envFiles.value.findIndex(({ file: fileInfo }) => fileInfo?.name === name)

  if (targetFileIndex !== -1) {
    envFiles.value.splice(targetFileIndex, 1)
  }

  emit("remove", name)
}

// Initialize inclusion state when files are detected or uploaded
watch([() => filePreviewRef.value?.envFiles, envFiles], (fileRecords, envFileList) => {
  if (fileRecords) {
    // Set default inclusion state for detected files (excluded by default)
    Object.keys(fileRecords).forEach((fileName) => {
      if (!(fileName in envFileInclusion.value)) {
        envFileInclusion.value[fileName] = false // Exclude by default
      }
    })
  }

  // Set default inclusion state for uploaded files (excluded by default)
  ;(envFileList as unknown as UploadFileInfo[]).forEach((file) => {
    if (!file) {
      return
    }

    if (file.name && !(file.name in envFileInclusion.value)) {
      envFileInclusion.value[file.name] = false // Exclude by default
    }
  })
}, { deep: true })

// Sync environment file inclusion state with the model
watch(envFileInclusion, (newInclusion) => {
  model.value.envFileInclusion = { ...newInclusion }
}, { deep: true })

watch(() => filePreviewRef?.value?.envFiles, (newFiles) => {
  model.value.envFileContent = { ...newFiles }
}, { deep: true })

function handleEnvInclusionUpdate(inclusion: Record<string, boolean>) {
  envFileInclusion.value = { ...inclusion }
}

function handleEnvEditedContentsUpdate(editedContents: Record<string, string>) {
  // Merge the edited contents into the existing contents
  if (!filePreviewRef.value) {
    return
  }
  const { envFiles } = filePreviewRef.value

  if (envFiles) {
    Object.assign(envFiles, editedContents)
  }
  else {
    filePreviewRef.value.envFiles = editedContents
  }
}

const hasEnvFile = computed(() => {
  const { root } = zipContent.value || {}
  const envFiles = filePreviewRef.value?.envFiles
  if (!envFiles) {
    return false
  }
  if (root) {
    return Boolean(envFiles[`${root}.env`])
  }
  return envFiles[".env"]
})

onMounted(() => {
  emit("update:form-ref", formRef.value)
})

onUnmounted(() => {
  unsubscribe()
})
</script>

<style lang="sass" scoped>
@use "@styles/sass/drag-area" as *
</style>

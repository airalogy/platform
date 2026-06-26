<template>
  <div class="overflow-auto bg-white text-black">
    <div class="mx-auto max-w-6xl p-6">
      <!-- Welcome Section -->
      <div class="mb-8">
        <div class="mb-2 text-sm font-medium uppercase text-gray-500">
          {{ $t("editor.landing.eyebrow") }}
        </div>
        <div class="flex items-center space-x-3">
          <n-icon size="32" class="text-primary">
            <code-icon />
          </n-icon>
          <h1 class="text-3xl font-light">
            {{ $t("editor.landing.title") }}
          </h1>
        </div>
        <p class="mt-3 max-w-3xl text-sm leading-6 text-gray-500">
          {{ $t("editor.landing.description") }}
        </p>
      </div>

      <!-- Action Cards -->
      <div class="lg:col-span-2 space-y-6">
        <section class="space-y-4">
          <h2 class="text-sm text-gray-500 font-medium tracking-wide uppercase">
            {{ $t("editor.landing.startLabel") }}
          </h2>
          <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <!-- Define a reusable template for action cards -->
            <define-action-card>
              <template #default="{ icon, title, description, onClick }">
                <n-button
                  quaternary
                  class="h-auto flex items-center justify-start p-3 space-x-3 hover:bg-gray-100"
                  color="black"
                  @click="onClick"
                >
                  <template #icon>
                    <n-icon size="20">
                      <component :is="iconMap[icon]" />
                    </n-icon>
                  </template>
                  <div class="text-left">
                    <div class="font-medium">
                      {{ title }}
                    </div>
                    <div class="text-sm text-gray-500">
                      {{ description }}
                    </div>
                  </div>
                </n-button>
              </template>
            </define-action-card>

            <reuse-action-card
              icon="file-plus"
              :title="$t('editor.landing.actions.template.title')"
              :description="$t('editor.landing.actions.template.description')"
              :on-click="handleNewProtocol"
            />

            <reuse-action-card
              icon="hub"
              :title="$t('editor.landing.actions.hub.title')"
              :description="$t('editor.landing.actions.hub.description')"
              :on-click="handleOpenHub"
            />

            <reuse-action-card
              icon="git-fork"
              :title="$t('editor.landing.actions.clone.title')"
              :description="$t('editor.landing.actions.clone.description')"
              :on-click="handleCloneRepo"
            />

            <reuse-action-card
              icon="folder-plus"
              :title="$t('editor.landing.actions.upload.title')"
              :description="$t('editor.landing.actions.upload.description')"
              :on-click="handleOpenFolder"
            />
          </div>
        </section>
      </div>
    </div>

    <!-- Protocol Template Dialog -->
    <protocol-template-dialog
      v-model:show="showTemplateDialog"
      :project-id="projectId"
      @create="handleCreateTemplate"
    />

    <!-- Upload Protocol Zip Modal -->
    <n-modal
      v-model:show="uploadModalVisible"
      preset="dialog"
      :title="$t('editor.landing.uploadTitle')"
      class="min-w-80vw"
      content-class="max-h-70vh overflow-y-auto"
    >
      <protocol-upload-form
        ref="uploadFormRef"
        v-model:model="uploadModel"
        :protocol-data="protocolData"
        upload-type="upload-zip"
        :check-id="false"
        @update:form-ref="handleFormRefUpdate"
        @loaded:content="handleContentLoaded"
      />
      <template #action>
        <n-button type="primary" :loading="isUploading" @click="processUploadForm">
          {{ $t("editor.landing.uploadApply") }}
        </n-button>
      </template>
    </n-modal>

    <!-- Protocol Reuse Modal -->
    <n-modal v-model:show="reuseModalVisible" preset="card" :title="$t('editor.landing.cloneTitle')" class="w-180">
      <n-alert :title="$t('editor.landing.cloneTitle')" type="info" class="mb-4">
        {{ $t("editor.landing.cloneDescription") }}
      </n-alert>
      <project-selector
        class="p-3"
        @update:lab="handleSourceLabUpdate"
        @update:project="handleSourceProjectUpdate"
        @update:node="handleSourceNodeUpdate"
      />
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="reuseModalVisible = false">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button type="primary" :disabled="!selectedSourceNode" :loading="isCloning" @click="handleCloneProtocol">
            {{ $t("editor.landing.cloneAction") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { Lab, Project } from "@/components/apply-steps/project-selector.vue"
import type { UploadContent } from "@airalogy/components/monaco-editor/types/upload"
import type { ProtocolModels } from "@airalogy/shared/types"

import type { FormInst } from "naive-ui"
import { useOrProvideApplyProtocol } from "@/components/apply-steps/composables/useApplyProtocolState"
import ProjectSelector from "@/components/apply-steps/project-selector.vue"
import ProtocolUploadForm from "@/components/hub/protocol-upload-form.vue"
import { useRouterPush } from "@/composables"
import { postReuseProtocol } from "@/service/api/project-protocols"
import { useFileUpload } from "@airalogy/components/monaco-editor/composables/useFileUpload"
import { handleContentLoaded as handleProtocolContentLoaded, processProtocolZipWorkflow } from "@airalogy/components/monaco-editor/utils/protocolContentLoader"
import { useThemeStore } from "@airalogy/composables/theme"
import { $t } from "@airalogy/shared/locales"

// Composables
import { createReusableTemplate } from "@vueuse/core"
// Stores
import { useUploadFileDataStore } from "@airalogy/components/monaco-editor/store/uploadFileDataStore"

import { useWebContainerStore } from "@airalogy/components/monaco-editor/store/webContainerStore"
// UI Components
import {
  NAlert,
  NButton,
  NIcon,
  NModal,
  useMessage,
} from "naive-ui"
import { nanoid } from "nanoid"
import { storeToRefs } from "pinia"
import { onMounted, ref } from "vue"
import { useRoute } from "vue-router"
import ProtocolTemplateDialog from "./protocol-template-dialog.vue"

// Icons
import HubIcon from "~icons/local/hub"
import CodeIcon from "~icons/tabler/code"
import FilePlusIcon from "~icons/tabler/file-plus"
import FolderPlusIcon from "~icons/tabler/folder-plus"
import GitForkIcon from "~icons/tabler/git-fork"

const props = withDefaults(defineProps<IProps>(), {
  uploadPackage: () => Promise.resolve(),
})

interface IProps {
  uploadPackage?: () => Promise<void>
}
// Create reusable ActionCard template
const [DefineActionCard, ReuseActionCard] = createReusableTemplate<{
  icon: "file-plus" | "folder-plus" | "git-fork" | "hub"
  title: string
  description: string
  onClick: () => void
}>()

// Icon mapping
const iconMap = {
  "file-plus": FilePlusIcon,
  "folder-plus": FolderPlusIcon,
  "git-fork": GitForkIcon,
  "hub": HubIcon,
}

// Theme
const themeStore = useThemeStore()
// Dark mode has been removed from the project

// Stores
const uploadFileDataStore = useUploadFileDataStore()
const webContainerStore = useWebContainerStore()
const { createFromTemplate } = uploadFileDataStore
const { initWebContainer } = webContainerStore
const { fileData, rootPath } = storeToRefs(uploadFileDataStore)

// Protocol state provider
const {
  protocolData,
  uploadModel,
  selectedOption,
  packageContent,
} = useOrProvideApplyProtocol()

// Router
const route = useRoute()
const { routerPushByKey } = useRouterPush()

// Project ID for template creation
const projectId = ref(nanoid())

// File upload utilities
const { processZipFile, isUploading } = useFileUpload()

// UI state
const showTemplateDialog = ref(false)
const uploadModalVisible = ref(false)
const reuseModalVisible = ref(false)
const message = useMessage()

// Clone protocol state
const selectedSourceLab = ref<Lab | null>(null)
const selectedSourceProject = ref<Project | null>(null)
const selectedSourceNode = ref<ProtocolModels.ProjectProtocolInfo | null>(null)
const isCloning = ref(false)

// Form refs
const uploadFormRef = ref<InstanceType<typeof ProtocolUploadForm> | null>(null)
const formRef = ref<FormInst | null>(null)

// ===== Handlers =====

// Modal handlers
function handleNewProtocol() {
  showTemplateDialog.value = true
}

function handleOpenFolder() {
  // Set the option type to upload-zip for the protocol state
  selectedOption.value = "upload-zip"

  // Show the upload modal
  uploadModalVisible.value = true
}

function handleCloneRepo() {
  // Reset selection state
  selectedSourceLab.value = null
  selectedSourceProject.value = null
  selectedSourceNode.value = null
  reuseModalVisible.value = true
}

function handleOpenHub() {
  void routerPushByKey("hub")
}

function handleSourceLabUpdate(lab: Lab | null) {
  selectedSourceLab.value = lab
}

function handleSourceProjectUpdate(project: Project | null) {
  selectedSourceProject.value = project
}

function handleSourceNodeUpdate(node: ProtocolModels.ProjectProtocolInfo | null) {
  selectedSourceNode.value = node
}

async function handleCloneProtocol() {
  if (!selectedSourceNode.value) {
    message.warning($t("editor.landing.selectProtocolWarning"))
    return
  }

  isCloning.value = true
  try {
    const { id: sourceProtocolId, name: protocolName } = selectedSourceNode.value
    const { labUid, projectUid } = route.params as { labUid?: string, projectUid?: string }

    if (!labUid || !projectUid) {
      message.error($t("editor.landing.missingProjectError"))
      return
    }

    // Generate a unique name for the cloned protocol
    const timestamp = Date.now().toString(36)
    const clonedName = `${protocolName}_clone_${timestamp}`
    const clonedUid = clonedName.toLowerCase().replace(/\s+/g, "_")

    // Call API to reuse the protocol
    const result = await postReuseProtocol({
      sourceProtocolId: String(sourceProtocolId),
      targetProjectUUID: projectUid,
      name: clonedName,
      uid: clonedUid,
    })

    if (!result) {
      message.error($t("editor.landing.cloneFailed"))
      return
    }

    message.success($t("editor.landing.cloneSuccess", { name: protocolName }))
    reuseModalVisible.value = false

    // Navigate to the new protocol
    routerPushByKey("protocol-info", {
      params: {
        labUid,
        projectUid,
        protocolUid: result.uid,
      },
    })
  }
  catch (error) {
    console.error("Error cloning protocol:", error)
    message.error($t("editor.landing.cloneFailed"))
  }
  finally {
    isCloning.value = false
  }
}

function handleFormRefUpdate(form: FormInst | null) {
  formRef.value = form
}

// Content handlers
function handleContentLoaded(content: UploadContent) {
  handleProtocolContentLoaded(content as any, uploadModel, protocolData, packageContent)
}

// Protocol actions
async function handleCreateTemplate(template: { type: string, name: string, version: string }) {
  try {
    // Set packageId before creating template
    uploadFileDataStore.packageId = projectId.value

    // Create protocol from template
    await createFromTemplate({
      type: template.type,
      name: template.name,
      version: template.version,
    })

    // Initialize web container with the new files
    await initWebContainer(projectId.value, fileData, rootPath.value, props.uploadPackage)

    // Navigate to the editor
    await navigateToEditor()

    message.success($t("editor.landing.createSuccess", { name: template.name }))
  }
  catch (error) {
    console.error("Error creating protocol:", error)
    message.error($t("editor.landing.createFailed"))
  }
}

async function processUploadForm() {
  try {
    // Validate form
    if (formRef.value) {
      await formRef.value.validate()
    }

    // Get file from model
    const file = uploadModel.value.fileList[0]?.file
    if (!file) {
      message.warning($t("editor.landing.uploadSelectWarning"))
      return
    }

    // Make sure the file is set in the uploadModel
    uploadModel.value.file = file

    // Use the unified protocol processing workflow
    const result = await processProtocolZipWorkflow(
      file,
      uploadModel,
      protocolData,
      processZipFile,
    )

    if (!result.success) {
      throw result.error
    }

    // If we have protocol data with metadata, update the uploadModel metadata
    if (protocolData.value?.metadata?.airalogy_protocol) {
      const metadata = protocolData.value.metadata.airalogy_protocol
      uploadModel.value.metadata = {
        ...uploadModel.value.metadata,
        ...metadata,
      }

      // Update version if available
      if (metadata.version) {
        uploadModel.value.version = metadata.version
      }
    }

    // Initialize web container with processed data
    await initWebContainer(projectId.value, fileData, rootPath.value, props.uploadPackage)

    // Navigate to editor
    await navigateToEditor()

    message.success($t("editor.landing.uploadSuccess"))
    uploadModalVisible.value = false
  }
  catch (error) {
    console.error("Error processing upload:", error)
    message.error($t("editor.landing.uploadFailed"))
  }
}

// Helper navigation function
function navigateToEditor() {
  // Get lab and project info from current route params (if available)
  const { labUid, projectUid } = route.params as {
    labUid?: string
    projectUid?: string
  }

  const query = {
    package_id: projectId.value,
    from_landing: "true",
    open_file: "protocol/protocol.aimd",
  }

  // For new protocols, we use a placeholder protocolUid to match the route pattern
  // The actual route will use query params (package_id) to identify the draft
  if (labUid && projectUid) {
    return routerPushByKey("protocol-editor", {
      params: {
        labUid,
        projectUid,
        protocolUid: "new", // Placeholder for route pattern
        protocolVersion: "",
      },
      query,
    })
  }

  return routerPushByKey("protocol-editor-playground", { query })
}

// Initialization
onMounted(() => {
  // Set up protocol state
  selectedOption.value = "upload-zip"

  // Check for template dialog query param
  const showDialog = route.query.show_template === "true"
  if (showDialog) {
    showTemplateDialog.value = true
  }
})
</script>

<template>
  <editor-layout
    ref="editorRef"
    v-model:is-preview-mode="isPreviewMode"
    v-model:is-full-screen="isFullScreen"
    :loading="loading" :protocol-info="protocolInfo" :side-menus="sideMenus" :emit-zip="false" :package-id="packageId" :reload-flag="reloadFlag" :is-read-only="isReadOnly" @save:dry="handleSaveProtocol" @new-file="handleNewProtocol"
  >
    <template #editor>
      <div class="relative size-full">
        <aimd-editor
          v-show="showAimdEditor"
          v-model="liveProtocolContent"
          :readonly="isReadOnly"
          class="size-full"
          :min-height="0"
          :show-top-bar="true"
          :show-toolbar="true"
          :show-aimd-toolbar="true"
          :show-md-toolbar="true"
          @update:model-value="handleAimdEditorChange"
        />
        <split-editor
          v-show="!showAimdEditor"
          :editor-id="0"
          :split-state="splitState"
          class="absolute inset-0"
        />
      </div>
    </template>
    <template #title>
      <protocol-title-section
        v-if="protocolInfo"
        :protocol-info="protocolInfo"
        class="absolute w-full justify-center px-60"
        content-class="!flex-grow-0 flex-basis-auto"
        size="tiny"
        is-protocol-link
        :breadcrumbs="breadcrumbs"
        :show-version="isReadOnly"
      >
        <template #prefix-icon="{ iconSize }">
          <n-icon :size="iconSize" class="mr-2">
            <icon-local-protocol />
          </n-icon>
        </template>
      </protocol-title-section>
    </template>
    <template #landing>
      <landing-page class="size-full flex-center" />
    </template>
    <template #raw>
      <n-spin :show="false" class="size-full" content-class="size-full !p-0">
        <div class="relative">
          <aimd-markdown-preview
            ref="rawRef"
            :content="liveProtocolContent"
            :mermaid-component="MermaidBlock"
            :resolve-url="resolveProtocolFile"
            body-class="markdown-body"
            mode="preview"
          />
          <protocol-bubble-menu
            v-if="rawRef?.rootElement"
            :container-ref="rawRef.rootElement"
          />
        </div>
      </n-spin>
    </template>
    <template #preview>
      <n-spin v-if="fieldRecordDefault" :show="false" class="size-full" content-class="size-full !p-0">
        <n-form
          class="platform-aimd-form-preview"
          :rules="fieldRecordDefault.rules"
          :model="previewFieldModel"
        >
          <aimd-markdown-preview
            ref="previewRef"
            :content="liveProtocolContent"
            :value="previewFieldModel"
            :render-options="aimdEditRenderOptions"
            :mermaid-component="MermaidBlock"
            :resolve-url="resolveProtocolFile"
            body-class="markdown-body"
            mode="edit"
            @render:result="handleFieldRendered"
          />
          <protocol-bubble-menu
            v-if="previewRef?.rootElement"
            :container-ref="previewRef.rootElement"
          />
        </n-form>
      </n-spin>
    </template>
  </editor-layout>

  <n-modal
    v-model:show="isShown"
    preset="card"
    title="Save Protocol"
    :bordered="false"
    size="huge"
    class="min-w-160 w-70vw"
    content-class="px-4 max-h-50vh overflow-y-auto mb-4"
    footer-class="flex items-center justify-end gap-4"
    :mask-closable="false"
  >
    <protocol-setup ref="protocolSetupRef" mode="reuse" :skip-upload="true" :protocol-info="protocolInfo" :disable-default="false" />
    <template #footer>
      <n-button size="medium" :disabled="loading" @click="hideModal">
        Cancel
      </n-button>
      <n-button
        size="medium"
        type="primary"
        :disabled="loading"
        :loading="loading"
        @click="handleApplyProtocol"
      >
        Save
      </n-button>
    </template>
  </n-modal>

  <!-- Assigner Progress Modal -->
  <assigner-progress-modal
    :state="assignerProgressState"
    @close="handleAssignerProgressClose"
  />
</template>

<script lang="ts" setup>
import type { IEmits as AIMDEmits, IAIMDWrapperProps } from "@/components/custom/aimd/types/aimd-types"
import type { BreadcrumbSection } from "@/components/Layout/protocol-title-section.vue"
import type { ProtocolData } from "@/constants/protocol"
import type { AimdTemplateEnv, BaseNode, RenderMode } from "@airalogy/aimd-core/types"
import type { ExposeState } from "@airalogy/components/monaco-editor/layout.vue"
import type { DiffModelInfo, ModelInfo } from "@airalogy/components/monaco-editor/store/editorStore"
import type { ISideMenuItem } from "@airalogy/components/src/monaco-editor/utils/sideMenus"
import type { IRecordDataKey, ProtocolModels } from "@airalogy/shared"
import type { ValidateError } from "async-validator"
import type { FormInst } from "naive-ui"
import type { FormValidate } from "naive-ui/es/form/src/interface"
import { useProvideApplyProtocol } from "@/components/apply-steps/composables/useApplyProtocolState"
import ProtocolSetup from "@/components/apply-steps/protocol-setup.vue"
import { createPlatformAimdFormRenderers } from "@/components/custom/aimd/composables/createPlatformAimdFormRenderers"
import ProtocolTitleSection from "@/components/Layout/protocol-title-section.vue"
import ProtocolInfoCard from "@/components/protocol/protocol-info-card.vue"
import { useBoolean, useClosableMessage, useLoading, useNaiveForm, useRouterPush, useShowModal } from "@/composables"
import { DEFAULT_FILE_ID_MAP } from "@/constants/protocol"
import { $t } from "@/locales"
import { getDownloadPackage, getDownloadPackageData } from "@/service/api/project-protocols"
import { postEditorSyntaxCheck } from "@/service/api/protocol"
import { extractProtocolInstructionFile, generateProtocolAimd, generateProtocolAssigner, generateProtocolModel, postEditorCodeEdit } from "@/service/api/protocol-generate"
import { useAuthStore } from "@/store/modules/auth"
import { resolveProtocolFile as resolveProtocolFileUtil } from "@/utils/resolveProtocolFile"
import { AimdEditor } from "@airalogy/aimd-editor/vue"
import { AimdMarkdownPreview } from "@airalogy/aimd-renderer/vue"
import { useChatProvider } from "@airalogy/components/chat/providers/useChatProvider"
import MermaidBlock from "@airalogy/components/markdown-editor/modules/mermaid/mermaid-block.vue"
import { useFileUpload } from "@airalogy/components/monaco-editor/composables/useFileUpload"
import EditorLayout from "@airalogy/components/monaco-editor/layout.vue"
import SplitEditor from "@airalogy/components/monaco-editor/split-editor.vue"
import { isNormalModelInfo, useActiveEditorStore, useModelsStore, useSplitStore } from "@airalogy/components/monaco-editor/store/editorStore"
import { useUploadFileDataStore } from "@airalogy/components/monaco-editor/store/uploadFileDataStore"
import ProtocolBubbleMenu from "@airalogy/components/protocol-bubble-menu.vue"
import { isDirectory, isFile, saveProjectData } from "@airalogy/components/src/monaco-editor/utils"
import { processUpdatedTomlContent } from "@airalogy/components/src/monaco-editor/utils/protocolContentLoader"
import { defaultSideMenus } from "@airalogy/components/src/monaco-editor/utils/sideMenus"
import { getFileExtensionFromBasename, getMIMEByExtension } from "@airalogy/shared/utils"
import { formatValidateErrors } from "@airalogy/shared/utils/errorFormatter.js"
import { useRouteQuery } from "@vueuse/router"

import IconLock from "~icons/tabler/lock"
import Big from "big.js"
import { cloneDeepWith as _cloneDeepWith } from "lodash-es"
import { NButton, NEllipsis, NIcon, NTag, useDialog } from "naive-ui"
import { nanoid } from "nanoid"
import { storeToRefs } from "pinia"
import { useAIMDProvide } from "../../components/custom/aimd/composables/useAIMDHelpers"
import { useProvideProtocolInfoStore } from "../project-protocols/hooks/useProtocolInfoStore"
import AssignerProgressModal from "../project-protocols/modules/protocol/components/AssignerProgressModal.vue"
import { useAssignerManagement } from "../project-protocols/modules/protocol/composables/useAssignerManagement"
import { getAssignerProgress } from "../project-protocols/modules/protocol/composables/useAssignerProgress"
import { useFieldParser } from "../project-protocols/modules/protocol/composables/useFieldParser"
import { useFieldState } from "../project-protocols/modules/protocol/composables/useFieldState"
import { useTableManagement } from "../project-protocols/modules/protocol/composables/useTableManagement"
import { useProvideProtocolEditorContext } from "./composables/useProtocolEditorContext"
import LandingPage from "./modules/landing.vue"

defineOptions({
  name: "EditorView",
})

const route = useRoute()
const { routerPushByKey, toHome, routerReplace, router } = useRouterPush()

// Provide editor context for all child components
const editorContext = useProvideProtocolEditorContext(route)

const { protocolInfo, fetchProtocolInfoByUid } = useProvideProtocolInfoStore(null)
const isReadOnly = ref(true)
const isFullScreen = ref(false)

const reloadFlag = ref(false)

const dialog = useDialog()
const { loading, startLoading, endLoading } = useLoading()

const breadcrumbs = computed(() => {
  const breadcrumbs: BreadcrumbSection[] = []
  if (!protocolInfo.value) {
    return []
  }
  // Use protocol ID from protocol.toml if available
  const { id, airalogy_id, name, uid } = protocolInfo.value

  if (isReadOnly.value) {
    breadcrumbs.push({
      id: nanoid(),
      text: () => h(NButton, {
        ghost: true,
        size: "tiny",
        iconPlacement: "right",
        onClick: () => handleNewProtocol("copy"),
      }, {
        icon: () => h(NIcon, {
          size: 16,
          component: IconLock,
        }),
        default: () => h(NEllipsis, { class: "max-w-40", style: "direction: rtl;" }, { default: () => uid }),
      }),
      visible: true,
      hideSeparator: true,
      tooltip: () => protocolInfo.value ? h(ProtocolInfoCard, { protocolInfo: protocolInfo.value, title: $t("page.protocol.protocolDetails") }) : "Click to edit",
      isPopup: true,
    })
  }
  else if (route.query.package_id) {
    // Check if we're editing a copy (has package_id but also has protocolInfo from original)
    const packageIdValue = route.query.package_id as string
    const isCopy = !!protocolInfo.value && packageIdValue !== uid

    breadcrumbs.push({
      id: packageIdValue,
      text: () => h("div", { class: "flex items-center gap-2" }, [
        h("span", { class: "text-sm" }, isCopy ? `Copy of ${uid?.split(".").pop() || "Protocol"}` : packageIdValue),
        h(NTag, {
          size: "small",
          type: "warning",
          class: "ml-1",
        }, () => "Draft"),
      ]),
      visible: true,
      tooltip: isCopy ? `Editing a copy of "${name || uid}". Changes will not affect the original protocol.` : "Draft protocol (not saved yet)",
    })
  }
  else if (id) {
    // Protocol info from TOML takes priority if we're not in read-only mode
    breadcrumbs.push({
      id,
      text: () => h("div", [h("span", airalogy_id)]),
      visible: true,
      tooltip: name || "Protocol from protocol.toml",
    })
  }
  else {
    // Fallback: Generate a random ID if none of the above conditions are met
    const breadcrumbId = nanoid()

    breadcrumbs.push({
      id: breadcrumbId,
      text: () => h("div", [
        h("span", "Unfinished Protocol"),
        h(NTag, {
          size: "small",
          type: "default",
          class: "ml-2",
        }, () => "Draft"),
      ]),
      visible: true,
      tooltip: "No protocol ID defined",
    })
  }
  return breadcrumbs
})

const editorRef = ref<ExposeState | null>(null)
const packageId = useRouteQuery<string>("package_id")
const activeEditorStore = useActiveEditorStore()
const splitStore = useSplitStore()
const uploadFileDataStore = useUploadFileDataStore()
const { createInitialFileData, getFileById, getFileByPath } = uploadFileDataStore
const { processZipFile, compressFiles } = useFileUpload()
const { activeEditorId } = storeToRefs(activeEditorStore)
const { splitState } = storeToRefs(splitStore)
const { rootPath } = storeToRefs(uploadFileDataStore)

function normalizeProtocolAssetPath(src: string) {
  return src.replace(/^(\/|\.\/)+/, "")
}

function resolveLocalProtocolFile(src: string): { url: string } | null {
  const normalizedSrc = normalizeProtocolAssetPath(src)
  if (!normalizedSrc) {
    return null
  }

  const candidatePaths = [
    normalizedSrc,
    [rootPath.value, normalizedSrc].filter(Boolean).join("/"),
  ]

  const localFile = candidatePaths
    .map(path => getFileByPath(path))
    .find(item => item && isFile(item))

  if (!localFile || !isFile(localFile)) {
    return null
  }

  if (localFile.fileUrl) {
    return { url: localFile.fileUrl }
  }

  if (typeof localFile.content === "string") {
    return null
  }

  const extension = getFileExtensionFromBasename(localFile.name) || ""
  const mimeType = getMIMEByExtension(extension) || undefined
  const localUrl = URL.createObjectURL(new Blob([localFile.content], mimeType ? { type: mimeType } : undefined))
  localFile.fileUrl = localUrl

  return { url: localUrl }
}

// Resolve file paths for protocol assets
async function resolveProtocolFile(src: string): Promise<{ url: string } | null> {
  const localFile = resolveLocalProtocolFile(src)
  if (localFile) {
    return localFile
  }

  if (!protocolInfo.value?.id) {
    return null
  }

  return resolveProtocolFileUtil(normalizeProtocolAssetPath(src), protocolInfo.value.id)
}

const { protocolId, currentEditorProtocolContext } = useChatProvider()
const editorChatProtocolId = computed(() => protocolInfo.value?.id ? String(protocolInfo.value.id) : null)
const editorChatAiralogyId = computed(() => {
  if (protocolInfo.value?.airalogy_id) {
    return protocolInfo.value.airalogy_id
  }

  if (packageId.value) {
    return `airalogy.local.editor.${packageId.value}`
  }

  return "airalogy.local.editor"
})

const sideMenus = computed(() => defaultSideMenus.map((it): ISideMenuItem => {
  const componentProps: ISideMenuItem["componentProps"] = { ...it.componentProps, protocolInfo: protocolInfo.value }
  const result: ISideMenuItem = { ...it, componentProps }
  if (it.key === "airalogy") {
    componentProps.protocolId = editorChatProtocolId.value
    componentProps.airalogyId = editorChatAiralogyId.value
    componentProps.codeEdit = postEditorCodeEdit
  }
  if (it.key === "protocol-documents") {
    componentProps.generateAimd = generateProtocolAimd
    componentProps.generateModel = generateProtocolModel
    componentProps.generateAssigner = generateProtocolAssigner
    componentProps.extractInstructionFile = extractProtocolInstructionFile
    componentProps.postEditorSyntaxCheck = postEditorSyntaxCheck
  }

  return result
}))

const message = useClosableMessage()

const { isShown, showModal, hideModal } = useShowModal()
const { applyProtocol, uploadModel, protocolData, packageContent } = useProvideApplyProtocol("reuse", false, "upload-zip", 2)

const protocolSetupRef = ref<{ validate: () => Promise<void> } | null>(null)

async function handleApplyProtocol() {
  try {
    await protocolSetupRef.value?.validate()
  }
  catch (error) {
    if (!uploadModel.value.projectId) {
      message.error($t("page.hub.protocolUpload.projectRequired"))
      return
    }

    const errors = formatValidateErrors(error as ValidateError[])
    message.error(errors.join("\n"))
    return
  }

  startLoading()
  try {
    if (!protocolData.value || !uploadModel.value) {
      message.error("No protocol data found")
      return
    }

    // const data: ProtocolData = { ...protocolData.value, toml_config: uploadModel.value.tomlContent || "" }
    // const filename = uploadModel.value.protocolUid || "protocol"

    // const file = await convertProtocolToZip(data, filename)
    const result = await compressFiles(false, true)
    if (!result) {
      return
    }
    packageContent.value = {
      type: "zip",
      content: {
        items: result.items,
        root: result.root,
      },
      updated: true,
    }
    const res = await applyProtocol()
    if (res) {
      const { latest_version, project_uid, lab_uid, uid } = res
      // message.success(`Apply protocol with version v${latest_version} succeed`)
      hideModal()
      dialog.success({
        title: "Apply protocol succeed",
        content: `Redirect to new protocol version v${latest_version} now?`,
        positiveText: $t("common.confirm"),
        negativeText: $t("common.cancel"),
        onPositiveClick: () => routerPushByKey("protocol-detail", {
          params: {
            labUid: lab_uid!,
            projectUid: project_uid!,
            protocolUid: uid,
          },
        }),

      })
    }
  }
  catch (error) {
    message.error((error as Error)?.message || $t("page.protocol.apply.action.applyFailed"))
  }
  finally {
    endLoading()
  }
}

async function handleSaveProtocol() {
  if (isReadOnly.value) {
    handleNewProtocol("copy")
    return
  }
  // const tomlFile = getFileById(DEFAULT_FILE_ID_MAP.toml_config)

  const { fileData, updateFileItem, getFileByFilename } = uploadFileDataStore
  if (!fileData) {
    message.error("Failed to ")
    return
  }

  // CRITICAL FIX: Save all dirty editor models to fileData before reading
  // This ensures that any unsaved changes in the editor are persisted
  const modelsStore = useModelsStore()
  const { modelInfos } = storeToRefs(modelsStore)

  // Save each dirty model to fileData
  for (const modelInfo of modelInfos.value) {
    if (isNormalModelInfo(modelInfo) && modelInfo.isDirty) {
      const content = toRaw(modelInfo.model).getValue()
      const fileInData = getFileByFilename(modelInfo.name)

      if (fileInData) {
        console.log("[handleSaveProtocol] Saving dirty model to fileData:", modelInfo.name)
        await updateFileItem(fileInData.id, { content })

        // Clear dirty flag
        modelInfo.isDirty = false
        modelInfo.lastSavedVersionId = toRaw(modelInfo.model).getAlternativeVersionId()
        modelInfo.content = content
      }
    }
  }

  // Also save to OPFS if packageId exists
  if (packageId.value && fileData) {
    await saveProjectData(packageId.value, fileData, () => Promise.resolve())
    console.log("[handleSaveProtocol] Saved all changes to OPFS")
  }

  const data = protocolData.value || Object.fromEntries(Object.keys(DEFAULT_FILE_ID_MAP).map(key => [key, ""]).concat([["metadata", {}] as any])) as unknown as ProtocolData

  if (!protocolData.value) {
    protocolData.value = data
  }

  // Ensure uploadModel has lab and project info from editor context
  if (!uploadModel.value.labUid || !uploadModel.value.projectUid || !uploadModel.value.projectId) {
    uploadModel.value.labUid = editorContext.labUid.value
    uploadModel.value.projectUid = editorContext.projectUid.value
    uploadModel.value.projectId = editorContext.projectId.value
  }

  fileData.forEach((item) => {
    if (isDirectory(item)) {
      return
    }
    const { id, content } = item
    if (typeof content !== "string") {
      return
    }

    if (id === DEFAULT_FILE_ID_MAP.toml_config) {
      uploadModel.value.tomlContent = content || ""
      processUpdatedTomlContent(uploadModel, protocolData)
    }
    else if (id === DEFAULT_FILE_ID_MAP.assigner) {
      data.assigner = content
    }
    else if (id === DEFAULT_FILE_ID_MAP.protocol) {
      data.protocol = content
    }
    else if (id === DEFAULT_FILE_ID_MAP.model) {
      data.model = content
    }
  })

  showModal()
}

async function handleNewProtocol(mode: "empty" | "copy") {
  const action = dialog.warning({
    title: mode === "empty" ? "Create empty protocol" : "Create copy of protocol",
    content: isReadOnly.value
      ? mode === "empty" ? "Are you sure you want to create a new protocol?" : "This protocol is in readonly mode. To make changes, you must first create a copy."
      : "Unsaved changes will be lost. Are you sure you want to create a new protocol?",
    positiveText: isReadOnly.value && mode === "copy" ? "Create Copy" : "Yes",
    negativeText: isReadOnly.value ? "Cancel" : "No",
    onPositiveClick: async () => {
      const id = nanoid()
      reloadFlag.value = true
      const prevId = packageId.value
      try {
        const { fileData, rootPath } = uploadFileDataStore

        await routerReplace({
          ...route,
          query: {
            ...route.query,
            package_id: id,
          },
        })

        reloadFlag.value = false

        const stop = watch(editorRef, async (val) => {
          if (!val) {
            return
          }
          const { handleInit } = val
          startLoading()
          try {
            if (mode === "empty") {
              await createInitialFileData(id, protocolInfo.value)
              await handleInit(id)
            }
            else {
              uploadFileDataStore.fileData = fileData
              uploadFileDataStore.rootPath = rootPath
              await saveProjectData(id, fileData || [], () => Promise.resolve())
              await handleInit(id, prevId, true)
            }
          }
          finally {
            endLoading()
            stop()
            isReadOnly.value = false
          }
        }, { immediate: true })
      }
      catch (error) {
        console.error(error)
      }
      finally {
        action.destroy()
      }
    },
  })
}

watch(protocolInfo, (val) => {
  if (isRef(protocolId)) {
    protocolId.value = val?.id || ""
  }
})

// Watch editor context and initialize uploadModel when ready
watch(
  () => editorContext.isReady.value,
  (ready) => {
    if (ready && editorContext.projectInfo.value) {
      const { labUid, projectUid, projectId } = editorContext
      uploadModel.value.labUid = labUid.value
      uploadModel.value.projectUid = projectUid.value
      uploadModel.value.projectId = projectId.value
    }
  },
  { immediate: true },
)

onMounted(async () => {
  startLoading()
  const { protocolUid, labUid, projectUid, protocolVersion } = route.params as {
    labUid: string
    projectUid: string
    protocolUid: string
    protocolVersion: string
  }

  let currPackageId = packageId.value as string
  // Only try to fetch protocol info if we don't have a package_id (not a new protocol)
  // and protocolUid is not a placeholder like "new" or a temporary ID (e.g., "protocol-xxx")
  const isTemporaryProtocolId = protocolUid?.startsWith("protocol-") && protocolUid.length > 20
  if (labUid && projectUid && protocolUid && !currPackageId && protocolUid !== "new" && !isTemporaryProtocolId) {
    try {
      const protocol = await fetchProtocolInfoByUid({
        labUid,
        projectUid,
        protocolUid,
        // Only pass version if it exists and is not empty
        version: protocolVersion || undefined,
      })

      if (!protocol) {
        // If fetch with version failed or returned null, try fetching the latest version
        // This handles the case where version might be invalid or not found
        const newestProtocol = await fetchProtocolInfoByUid({ labUid, projectUid, protocolUid })

        if (newestProtocol && !currPackageId) {
          routerReplace({
            ...route,
            // @ts-expect-error params is required
            params: {
              ...route.params,
              protocolVersion: newestProtocol.metadata.version || newestProtocol.latest_version,
            },
          })
        }
      }
    }
    catch (e) {
      // Fallback to fetching latest if the specific version fetch failed (e.g. 404)
      try {
        const newestProtocol = await fetchProtocolInfoByUid({ labUid, projectUid, protocolUid })
        if (newestProtocol && !currPackageId) {
          routerReplace({
            ...route,
            // @ts-expect-error params is required
            params: {
              ...route.params,
              protocolVersion: newestProtocol.metadata.version || newestProtocol.latest_version,
            },
          })
        }
      }
      catch (err) {
        // Only redirect to home if both attempts fail
        toHome()
      }
    }
  }

  await nextTick()

  // Function to initialize the editor once it's ready
  async function initializeEditor() {
    if (!editorRef.value) {
      return
    }

    try {
      const { handleInit } = editorRef.value
      if (!currPackageId) {
        if (protocolUid && protocolInfo.value?.id) {
        // Set readonly mode if protocolUUID is present but no package_id
          isReadOnly.value = true

          try {
            // Get download URL from backend
            const res = await getDownloadPackage(protocolInfo.value?.id, protocolVersion)

            // Download the actual file from OSS
            const data = res?.data?.url ? await getDownloadPackageData(res.data.url) : null

            if (data && data.size > 0) {
              await processZipFile(new File([data], "protocol.zip"))

              currPackageId = protocolUid as string
              const { fileData } = uploadFileDataStore

              // Save the processed files to OPFS so handleInit can load them
              if (fileData && fileData.length > 0) {
                await saveProjectData(currPackageId, fileData, () => Promise.resolve())
              }
              else {
                currPackageId = nanoid()
              }
            }
            else {
              currPackageId = nanoid()
            }
          }
          catch (e) {
            console.error("Error downloading/processing protocol:", e)
            currPackageId = nanoid()
          }
          // Don't automatically show the copy dialog, let user trigger it via the lock icon
          // handleNewProtocol("copy")
        }
        else {
          // Creating a new protocol - should not be in readonly mode
          isReadOnly.value = false
          currPackageId = nanoid()

          // Check if we're coming from the landing page with a template request
          const fromLanding = route.query.from_landing === "true" || (route.name as any) === "protocol-editor-playground"

          if (!fromLanding) {
            // If not from landing, redirect to landing with package_id
            routerPushByKey("protocol-editor", {
              query: {
                show_template: "true",
                package_id: currPackageId,
              },
            })
            endLoading()
            return
          }

          await createInitialFileData(currPackageId, protocolInfo.value)

          await router.replace({
            ...route,
            query: {
              package_id: currPackageId,
            },
          })
        }
      }
      else {
        isReadOnly.value = false
      }

      await handleInit(currPackageId)
    }
    catch (e) {
      message.error((e as Error)?.message)
    }
    finally {
      endLoading()
    }
  }

  // Wait for editorRef to be ready
  if (editorRef.value) {
    await initializeEditor()
  }
  else {
    const stop = watch(editorRef, async (val) => {
      if (val) {
        stop()
        await initializeEditor()
      }
    }, { immediate: true })
  }
})

const { bool: contentReady, setTrue: setContentReady } = useBoolean()
const { bool: modelLoading, setTrue: setModelLoading, setFalse: stopModelLoading } = useBoolean()

const protocolModel = computed(() => {
  const modelFile = getFileById(DEFAULT_FILE_ID_MAP.model)
  if (!modelFile) {
    return ""
  }

  return typeof modelFile.content === "string" ? modelFile.content : ""
})

const protocolAssigner = computed(() => {
  const assignerFile = getFileById(DEFAULT_FILE_ID_MAP.assigner)
  if (!assignerFile) {
    return ""
  }

  return typeof assignerFile.content === "string" ? assignerFile.content : ""
})

const protocolAIMD = computed(() => {
  const aimdFile = getFileById(DEFAULT_FILE_ID_MAP.protocol)
  if (!aimdFile) {
    return ""
  }

  return aimdFile.content as string
})

const liveProtocolContent = ref("")
const liveModelContent = ref("")
const liveAssignerContent = ref("")
const liveTomlContent = ref("")
const modelsStore = useModelsStore()
const { modelInfos } = storeToRefs(modelsStore)
const visibleEditorId = computed(() => activeEditorId.value >= 0 ? activeEditorId.value : splitState.value.findIndex(Boolean))

function findNormalModelInfo(
  infos: Array<ModelInfo | DiffModelInfo | null>,
  ids: string[],
): ModelInfo | null {
  const match = infos.find((info): info is ModelInfo =>
    info !== null
    && isNormalModelInfo(info)
    && ids.includes(info.id),
  )

  return match || null
}

const activeTextModelInfo = computed(() => {
  if (visibleEditorId.value < 0) {
    return null
  }

  const modelInfo = modelsStore.getActiveModelInfo(visibleEditorId.value, "normal")
  return isNormalModelInfo(modelInfo || {}) ? modelInfo : null
})
const showAimdEditor = computed(() => {
  const activeFileId = activeTextModelInfo.value?.id
  const activeFileName = activeTextModelInfo.value?.name

  if (!activeFileId && !activeFileName) {
    return true
  }

  return activeFileId === DEFAULT_FILE_ID_MAP.protocol || activeFileName === "protocol.aimd"
})

// Sync AimdEditor content changes back to Monaco editor store model
let isSyncingFromAimdEditor = false
function handleAimdEditorChange(value: string) {
  const infos = modelInfos.value
  const protocolModelInfo = findNormalModelInfo(infos, ["protocol.aimd", DEFAULT_FILE_ID_MAP.protocol])
  if (protocolModelInfo?.model && !isSyncingFromAimdEditor) {
    isSyncingFromAimdEditor = true
    const currentValue = protocolModelInfo.model.getValue()
    if (currentValue !== value) {
      protocolModelInfo.model.setValue(value)
    }
    isSyncingFromAimdEditor = false
  }
}
const disposeListener = ref<(() => void) | null>(null)
const disposeModelListener = ref<(() => void) | null>(null)
const disposeAssignerListener = ref<(() => void) | null>(null)
const disposeTomlListener = ref<(() => void) | null>(null)

watch(protocolAIMD, (val) => {
  if (val && !liveProtocolContent.value) {
    liveProtocolContent.value = val
  }
}, { immediate: true })

watch(modelInfos, (infos) => {
  // Monitor protocol.aimd changes - use filename instead of FILE_ID_MAP
  const protocolModelInfo = findNormalModelInfo(infos, ["protocol.aimd", DEFAULT_FILE_ID_MAP.protocol])

  if (protocolModelInfo?.model) {
    if (disposeListener.value) {
      disposeListener.value()
    }

    // Set initial content
    const initialContent = protocolModelInfo.model.getValue()
    if (initialContent) {
      liveProtocolContent.value = initialContent
    }

    const disposable = protocolModelInfo.model.onDidChangeContent(() => {
      if (!isSyncingFromAimdEditor) {
        liveProtocolContent.value = protocolModelInfo.model!.getValue()
      }
    })
    disposeListener.value = () => disposable.dispose()
  }

  // Monitor model.py changes - use filename instead of FILE_ID_MAP
  const modelModelInfo = findNormalModelInfo(infos, ["model.py", DEFAULT_FILE_ID_MAP.model])

  if (modelModelInfo?.model) {
    if (disposeModelListener.value) {
      disposeModelListener.value()
    }

    liveModelContent.value = modelModelInfo.model.getValue()

    const disposable = modelModelInfo.model.onDidChangeContent(() => {
      liveModelContent.value = modelModelInfo.model!.getValue()
    })
    disposeModelListener.value = () => disposable.dispose()
  }

  // Monitor assigner.py changes - use filename instead of FILE_ID_MAP
  const assignerModelInfo = findNormalModelInfo(infos, ["assigner.py", DEFAULT_FILE_ID_MAP.assigner])

  if (assignerModelInfo?.model) {
    if (disposeAssignerListener.value) {
      disposeAssignerListener.value()
    }

    liveAssignerContent.value = assignerModelInfo.model.getValue()

    const disposable = assignerModelInfo.model.onDidChangeContent(() => {
      liveAssignerContent.value = assignerModelInfo.model!.getValue()
    })
    disposeAssignerListener.value = () => disposable.dispose()
  }

  // Monitor protocol.toml changes - use filename instead of FILE_ID_MAP
  const tomlModelInfo = findNormalModelInfo(infos, ["protocol.toml", DEFAULT_FILE_ID_MAP.toml_config])

  if (tomlModelInfo?.model) {
    if (disposeTomlListener.value) {
      disposeTomlListener.value()
    }

    // Set initial content
    const initialTomlContent = tomlModelInfo.model.getValue()
    if (initialTomlContent) {
      liveTomlContent.value = initialTomlContent
    }

    const disposable = tomlModelInfo.model.onDidChangeContent(() => {
      liveTomlContent.value = tomlModelInfo.model!.getValue()
    })
    disposeTomlListener.value = () => disposable.dispose()
  }
}, { deep: true, immediate: true })

onBeforeUnmount(() => {
  if (disposeListener.value) {
    disposeListener.value()
  }
  if (disposeModelListener.value) {
    disposeModelListener.value()
  }
  if (disposeAssignerListener.value) {
    disposeAssignerListener.value()
  }
  if (disposeTomlListener.value) {
    disposeTomlListener.value()
  }
})

watch([
  liveProtocolContent,
  protocolAIMD,
  liveModelContent,
  protocolModel,
  liveAssignerContent,
  protocolAssigner,
  liveTomlContent,
  () => protocolInfo.value?.id,
  () => protocolInfo.value?.name,
  () => protocolInfo.value?.uid,
  packageId,
], () => {
  const aimd = liveProtocolContent.value || protocolAIMD.value || ""
  const modelPy = liveModelContent.value || protocolModel.value || ""
  const assignerPy = liveAssignerContent.value || protocolAssigner.value || ""
  const toml = liveTomlContent.value || ""
  const title = protocolInfo.value?.name || protocolInfo.value?.uid || packageId.value || "Current editor protocol"
  const enabled = Boolean(aimd.trim() || modelPy.trim() || assignerPy.trim() || toml.trim())

  currentEditorProtocolContext.value = {
    enabled,
    title,
    protocol_aimd: aimd,
    model_py: modelPy,
    assigner_py: assignerPy,
    protocol_toml: toml,
  }
}, { immediate: true })

const draftProtocolInfo = ref<ProtocolModels.ProtocolInfo | null | undefined>(null)

// AIMD preview

interface AimdMarkdownPreviewExpose {
  env: AimdTemplateEnv
  reload: () => Promise<void>
  rootElement: HTMLElement | null
}

const previewRef = ref<AimdMarkdownPreviewExpose>()
const rawRef = ref<AimdMarkdownPreviewExpose>()
const lastParsedAimd = ref("")

const { formRef, validate } = useNaiveForm()
const aimdRef = ref<{ formRef: FormInst | null, restoreTableVariableRecord: () => void } | null>(null)

function restoreValidation() {
  if (aimdRef.value?.formRef) {
    aimdRef.value.formRef.restoreValidation()
  }

  formRef.value?.restoreValidation()
}

const {
  // Models
  fieldModel,
  fieldRecordDefault,

  // Lists
  fieldPropList,
  scopeList,

  // Records
  refRecord,
  tableRecord,
  tableEmitterRecord,
  varScopeRecord,

  // Mounted State
  domMounted,
  setDomMounted,
  setDomUnMounted,

  // Restore Field Record
  restoreFieldRecord,
} = useFieldState(computed(() => ({
  protocol: draftProtocolInfo.value,
  protocolId: "",
})), liveProtocolContent)

const previewFieldModel = computed(() => fieldModel as unknown as Record<string, Record<string, unknown>>)

const { handleTableRowUpdate } = useTableManagement()

const { handleParseField } = useFieldParser(
  fieldModel,
  draftProtocolInfo,
  scopeList,
  fieldPropList,
  refRecord,
  tableRecord as any,
  tableEmitterRecord,
)

async function handleFieldRendered() {
  const content = liveProtocolContent.value
  if (domMounted.value && lastParsedAimd.value === content) {
    return
  }

  lastParsedAimd.value = content
  await nextTick()
  setDomMounted()

  // const sourceList = Array.from(
  //   document.querySelectorAll<HTMLSourceElement>(".markdown-body source") || [],
  // )

  // if (sourceList.length > 0) {
  //   void handleMedia(sourceList)
  // }

  // Access template environment data directly
  if (previewRef.value) {
    const { env } = previewRef.value

    // Call the field parser with the analysis data
    handleParseField(env)
  }
}

// Update template refs for table row updates
function handleTableRowActions(type: "add-row" | "remove-row", payload: any) {
  handleTableRowUpdate(type, payload, tableEmitterRecord, fieldModel)
}

const handleAssignerValidate: FormValidate = async (callback, shouldRuleBeApplied) => {
  if (aimdRef.value?.formRef) {
    try {
      await aimdRef.value.formRef.validate(() => {}, shouldRuleBeApplied)
    }
    catch (e) {
      // NOPE
    }
  }

  return await validate(callback, shouldRuleBeApplied)
}

// Create a ref to store the updateField function to resolve circular dependency
const updateFieldRef = ref<((fieldModel: any, payload: any) => Promise<void>) | null>(null)

// Create a wrapper function that calls updateField when available
async function updateFieldWrapper(fieldModel: any, payload: any) {
  if (updateFieldRef.value) {
    await updateFieldRef.value(fieldModel, payload)
  }
}

// Assigner progress modal
const { state: assignerProgressStateRaw, hide: hideAssignerProgress } = getAssignerProgress()
const assignerProgressState = assignerProgressStateRaw as unknown as InstanceType<typeof AssignerProgressModal>["$props"]["state"]
function handleAssignerProgressClose() {
  hideAssignerProgress()
}

/** Render aimd tokens to component */
const { handleAssigner, handleDependent, assignerLoadingRecord, assignerErrorRecord, handleAssignerCancel, assignerRequestRecord } = useAssignerManagement({
  protocolId: "",
  emit: () => {},
  varScopeRecord,
  validate: handleAssignerValidate,
  restoreValidation,
  shouldTrigger: true,
  updateField: updateFieldWrapper,
})

const aimdProps = computed((): IAIMDWrapperProps => ({
  protocolId: protocolId.value,
  record: fieldRecordDefault.value,
  propList: fieldPropList.value,
  scopeList: scopeList.value,
  typed: previewRef.value?.env?.typed as IAIMDWrapperProps["typed"],
  refRecord: refRecord.value,
  tableRecord: tableRecord.value,
  varScopeRecord: varScopeRecord.value,
  readonly: false,
  assignerLoadingRecord: assignerLoadingRecord.value,
  assignerErrorRecord: assignerErrorRecord.value,
  assignerRequestRecord: assignerRequestRecord.value,
}))

const aimdEmit: AIMDEmits = (event, ...args) => {
  if (event === "add-row:table") {
    handleTableRowActions("add-row", ...args)
  }
  if (event === "remove-row:table") {
    handleTableRowActions("remove-row", ...args)
  }
}

const { variableList, fieldEventBus, fieldModel: componentFieldModel } = useAIMDProvide(aimdProps, aimdEmit)

const isPreviewMode = ref(true)
// TODO: rename it
const mode = computed<RenderMode>(() => isPreviewMode.value ? "edit" : "preview")

// Map short scope codes to full scope names for unified renderers
const scopeMap: Record<string, string> = {
  rv: "research_variable",
  rs: "research_step",
  rc: "research_check",
  rt: "research_variable",
}

// Platform adapters only replace fields that need interactive form controls.
function getNodeProps(node: { id: string, scope: string, type?: string }) {
  const { id, scope, type } = node
  const fullScope = scopeMap[scope] || scope

  if (scope === "var_table" || scope === "rt") {
    return variableList.value.find(it => it.scope === "research_variable" && it.prop === id) || null
  }
  return variableList.value.find(it => it.scope === fullScope && it.prop === id && (!type || it.type === type)) || null
}

const aimdRenderersEdit = createPlatformAimdFormRenderers({
  getTokenProps: getNodeProps,
})
const aimdEditRenderOptions = { aimdRenderers: aimdRenderersEdit }

const authStore = useAuthStore()

watchEffect(() => {
  const { userInfo } = authStore
  const record = fieldRecordDefault.value
  const propList = fieldPropList.value
  if (!record || !record.field || !userInfo || !Array.isArray(propList) || propList.length === 0) {
    return []
  }
  const { field } = record

  scopeList.value.forEach((scopeName, idx) => {
    const scopePropList = propList[idx] as string[]

    scopePropList.forEach((prop) => {
      const item = field[scopeName]?.[prop]
      if (!item) {
        return
      }

      let val: any = _cloneDeepWith(toRaw(item.value), (objVal) => {
        if (objVal instanceof Big) {
          return new Big(objVal)
        }

        return undefined
      })

      if (!val && (scopeName === "research_check" || scopeName === "research_step")) {
        val = {
          annotation: "",
          // For research_step with check=True, initialize checked as false (unchecked)
          // For research_step without check or research_check, initialize as null
          checked: (scopeName === "research_step" && item.raw?.check)
            ? false
            : (scopeName === "research_check" ? false : null),
        }
      }
      if (componentFieldModel[scopeName]) {
        componentFieldModel[scopeName][prop] = { value: val }
      }
      else {
        componentFieldModel[scopeName] = { [prop]: { value: val } }
      }
    })
  })

  return () => { }
})

watch(
  fieldRecordDefault,
  (record) => {
    if (!record) {
      return
    }

    const propList = fieldPropList.value

    const { field } = record

    const batchList: { scope: IRecordDataKey, prop: string, value: any, assigner: any, dependent: any, info: any }[] = []

    scopeList.value.forEach((scopeName, idx) => {
      const scopePropList = propList[idx]
      scopePropList.forEach((prop) => {
        if (Array.isArray(prop)) {
          return
        }

        const item = field[scopeName]?.[prop]
        if (!item) {
          return
        }

        const { value: val, type, scope, assigner, dependent, info } = item

        if (typeof val !== "undefined" && val !== null) {
          if (!(
            ((type === "float" || type === "integer" || type === "number")
              && (val.value === null || typeof val.value === "undefined"))
              || (Array.isArray(val) && val.length === 0)
          )) {
            batchList.push({
              scope,
              prop,
              value: val,
              assigner,
              dependent,
              info,
            })
          }
        }
      })
    })

    void nextTick(() => {
      const batchId = nanoid()
      fieldEventBus.emit("preview-field-change-batch", {
        batchId,
        list: batchList,
      })
    })
  },
  { immediate: true },
)

// Watch protocolInfo and use it as draftProtocolInfo when available
watch(protocolInfo, (val) => {
  if (val && !draftProtocolInfo.value) {
    draftProtocolInfo.value = val as unknown as ProtocolModels.ProtocolInfo
    // Trigger field record restoration
    restoreFieldRecord()
  }
}, { immediate: true })

watch([protocolModel, liveProtocolContent, liveTomlContent, isPreviewMode], async ([modelCode, aimdContent, tomlContent, isPreviewModeVal], [prevModelCode, prevAIMDContent, prevTomlContent, prevIsPreviewModeVal]) => {
  // Skip if no content at all (initial state before loading)
  if (!aimdContent && !prevAIMDContent) {
    // Only set to null if model code is also empty
    if (!modelCode && !prevModelCode) {
      setContentReady()
      return
    }
  }

  if (modelCode === prevModelCode && aimdContent === prevAIMDContent && tomlContent === prevTomlContent && isPreviewModeVal === prevIsPreviewModeVal) {
    if (contentReady.value) {
      return
    }
  }

  try {
    if (isPreviewModeVal) {
      // Update protocol data when TOML changes
      if (tomlContent && tomlContent !== prevTomlContent) {
        uploadModel.value.tomlContent = tomlContent
        processUpdatedTomlContent(uploadModel, protocolData)
      }

      // Skip execution, directly update preview
      restoreFieldRecord()
      await nextTick()
      previewRef.value?.reload?.()
    }
    else {
      rawRef.value?.reload?.()
    }
  }
  catch (e) {
    console.error("[Editor Watch] Error:", e)
  }
  finally {
    setContentReady()
  }
}, { immediate: true })
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *

:deep(.n-form-item)
  position: relative

// :deep(.n-form-item-blank)
//   flex-direction: column

:deep(.n-input-wrapper)
  width: 100%

:deep(.n-form-item-label__text)
  flex: 1
:deep(.n-collapse-item__header-main)
  overflow: hidden
:deep(.n-form-item-label__text)
  overflow: hidden

// AimdEditor: remove border/radius, fill container
:deep(.aimd-editor)
  border: none
  border-radius: 0
  height: 100%

:deep(.aimd-editor-panel)
  display: flex
  flex-direction: column
  flex: 1
  min-height: 0
  overflow: hidden

:deep(.aimd-editor-panel > div)
  flex: 1
  min-height: 0
  height: 100%

:deep(.aimd-editor-source-mode),
:deep(.aimd-editor-wysiwyg-mode)
  height: 100% !important
</style>

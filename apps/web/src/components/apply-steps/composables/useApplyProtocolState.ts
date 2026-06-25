import type { ZipUpload } from "@airalogy/components/monaco-editor/types/upload"
import type { ProtocolData } from "@airalogy/shared/constants"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { ZipItem } from "@airalogy/shared/utils"
import type { Zippable } from "fflate"
import type { UploadFileInfo } from "naive-ui"
import type { ComputedRef, Ref } from "vue"
import { $t } from "@/locales"
import { postForkProtocol, postReuseProtocol, postUploadProtocol } from "@/service/api/project-protocols"
import { useOrProvideProjectInfoStore } from "@/views/project-protocols/hooks/useProjectInfoStore"
import { useOrProvideProtocolInfoStore } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import { ENV_EXTENSIONS, getNextRecommendedVersion, zipToPromise } from "@airalogy/shared/utils"
import { createInjectionState } from "@vueuse/core"
import { useRouteQuery } from "@vueuse/router"
import { computed, ref, watch } from "vue"

// Base model interface for common properties
interface BaseModel extends ProtocolModels.ApplyProtocolRequestPayload {
  labUid: string | null
  projectUid: string | null
  projectId?: string | null
  version: string
  description: string
  tags: string[]
  isPublic: boolean
  protocolUid: string | null
  protocolId: string | null
  metadata: ProtocolModels.ProtocolMetaData
}

export interface FormModel extends BaseModel {
  protocolName?: string
  // targetLabUid?: string | null
  // targetProjectUid?: string | null
  // targetProjectId?: string | null
}

export interface UploadModel extends BaseModel {
  fileList: UploadFileInfo[]
  file: File | null
  tomlContent: string | null
  envFileInclusion?: Record<string, boolean>
  envFileContent?: Record<string, string>
}

export enum ApplyStep {
  SelectMethod = 1,
  ProtocolSetup = 2,
  Details = 3,
  Success = 4,
}

export type ApplyOption = "existing" | "scratch" | "upload-zip" | "hub" | null

export interface ApplyProtocolState {
  activeModel: ComputedRef<FormModel | UploadModel>
  currentStep: Ref<ApplyStep>
  stepStatus: Ref<"process" | "finish" | "error">
  selectedOption: Ref<ApplyOption>
  isApplying: Ref<boolean>
  model: Ref<FormModel>
  uploadModel: Ref<UploadModel>
  protocolData: Ref<ProtocolData | null>
  isStepValid: ComputedRef<Record<ApplyStep, boolean>>
  applyProtocol: (payload?: FormModel | UploadModel) => Promise<ProtocolModels.ProtocolResponseInfo | undefined>
  applyResult: Ref<ProtocolModels.ProtocolResponseInfo | null>
  mode: "fork" | "reuse"
  packageContent: Ref<ZipUpload | null>
  protocolInfo: Ref<ProtocolModels.ProjectProtocolInfo | null>
  projectInfo: Ref<Api.Project.MyProjectInfo | null>
}

// Helper function to create initial model state
function createBaseModelState(protocolInfo?: ProtocolModels.ProjectProtocolInfo | null): BaseModel {
  const { lab, project, uid, id, metadata, airalogy_id, latest_version } = protocolInfo || {}

  const nextVersion = latest_version ? getNextRecommendedVersion(latest_version) : ""
  return {
    labUid: lab?.uid || null,
    projectUid: project?.uid || null,
    version: "",
    description: "",
    tags: [],
    isPublic: true,
    protocolUid: uid || null,
    protocolId: id || null,
    metadata: {
      id: uid || metadata?.id || "",
      version: nextVersion || metadata?.version || "",
      airalogy_protocol_id: airalogy_id || "",
      name: metadata?.name || "",
      authors: metadata?.authors || [],
      maintainers: metadata?.maintainers || [],
      disciplines: metadata?.disciplines || [],
      description: metadata?.description || "",
      keywords: metadata?.keywords || [],
      license: metadata?.license || "",
    },
  }
}
const encoder = new TextEncoder()

// Helper function to check if a file is an environment file
function isEnvironmentFile(filename: string): boolean {
  return ENV_EXTENSIONS.some(ext => filename.endsWith(ext))
}

// Helper function to filter out environment files from zip items
function filterEnvFiles(items: ZipItem[], filesToExclude: string[] = []): ZipItem[] {
  return items.filter((item) => {
    // If filesToExclude is provided, use that specific list
    if (filesToExclude.length > 0) {
      return !filesToExclude.some(excludeFile => item.name.endsWith(excludeFile) || item.path.endsWith(excludeFile))
    }
    // Otherwise, filter out all environment files (fallback behavior)
    return !isEnvironmentFile(item.name)
  })
}

function createFormModel(protocolInfo?: ProtocolModels.ProjectProtocolInfo | null, mode: "fork" | "reuse" = "reuse"): FormModel {
  return {
    ...createBaseModelState(protocolInfo),
    protocolUid: mode === "fork" ? null : protocolInfo?.uid || null,
    protocolName: "",
  }
}

function createUploadModel(protocolInfo?: ProtocolModels.ProjectProtocolInfo | null, mode: "fork" | "reuse" = "reuse"): UploadModel {
  return {
    ...createBaseModelState(protocolInfo),
    protocolUid: mode === "fork" ? null : protocolInfo?.uid || null,
    fileList: [],
    file: null,
    tomlContent: null,
  }
}

// Helper function to repackage a file with updated metadata
async function repackageFileWithMetadata(
  file: File,
  metadata: ProtocolModels.ProtocolMetaData,
  originalMetadata?: any,
): Promise<File> {
  // Check if metadata has changed
  if (originalMetadata
    && JSON.stringify(metadata) === JSON.stringify(originalMetadata)) {
    return file
  }

  // Create new file with updated metadata
  const content = await file.arrayBuffer()

  // Create a new filename that includes metadata version if available
  const fileExtension = file.name.split(".").pop()
  const newFileName = metadata.name
    ? `${metadata.name}-${metadata.version || "v1"}.${fileExtension}`
    : file.name

  return new File(
    [content],
    newFileName,
    { type: file.type },
  )
}

// Validation functions
const validators = {
  selectMethod: (option: ApplyOption) => !!option,

  protocolSetup: (option: ApplyOption, model: FormModel | UploadModel) => {
    if (option === "existing") {
      return !!(model as FormModel).labUid && !!(model as FormModel).projectUid
    }
    return option === "scratch" || option === "upload-zip"
      ? (model as UploadModel).fileList.length > 0
      : false
  },

  details: () => true,
  success: () => true,
}

function compareBuffer(first?: Uint8Array<ArrayBufferLike>, second?: Uint8Array<ArrayBufferLike>) {
  if (!first || !second) {
    return false
  }

  return first.length === second.length && first.every((value, index) => value === second[index])
}

const [useProvideApplyProtocol, _useApplyProtocol] = createInjectionState(
  (mode: "fork" | "reuse" = "reuse", routeQuery = true, defaultType: ApplyOption = null, defaultStep = 1): ApplyProtocolState => {
    const { protocolInfo } = useOrProvideProtocolInfoStore(null)
    const { projectInfo } = useOrProvideProjectInfoStore(null)

    const currentStep = routeQuery
      ? useRouteQuery<number>("step", defaultStep, {
        transform: (val: string | number) => {
          const num = typeof val === "string" ? Number.parseInt(val, 10) : val
          return Number.isNaN(num) ? defaultStep : num
        },
      })
      : ref(defaultStep)

    const selectedOption = routeQuery ? useRouteQuery<ApplyOption>("type", null) : ref(defaultType)
    const stepStatus = ref<"process" | "finish" | "error">("process")
    const isApplying = ref<boolean>(false)
    const model = ref<FormModel>(createFormModel(protocolInfo?.value, mode))
    const uploadModel = ref<UploadModel>(createUploadModel(protocolInfo?.value, mode))
    const protocolData = ref<ProtocolData | null>(null)
    const applyResult = ref<ProtocolModels.ForkedProtocolResponse | null>(null)
    const packageContent = ref<ZipUpload | null>(null)
    const activeModel = computed(() =>
      selectedOption.value === "existing" ? model.value : uploadModel.value,
    )

    const isStepValid = computed(() => ({
      [ApplyStep.SelectMethod]: validators.selectMethod(selectedOption.value),
      [ApplyStep.ProtocolSetup]: validators.protocolSetup(selectedOption.value, activeModel.value),
      [ApplyStep.Details]: validators.details(),
      [ApplyStep.Success]: validators.success(),
    }))

    watch(
      [currentStep, selectedOption],
      ([newStep, newType], [_oldStep, oldType]) => {
        if (newType === null && newStep !== 1) {
          currentStep.value = 1
          return
        }

        const protocolVal = protocolInfo?.value
        if (newStep === 1 || newType !== oldType) {
          selectedOption.value = newStep === 1 ? null : selectedOption.value
          model.value = createFormModel(protocolVal, mode)
          uploadModel.value = createUploadModel(protocolVal, mode)
          protocolData.value = null
        }
      },
      { immediate: true },
    )

    async function applyProtocol(payload?: FormModel | UploadModel) {
      const finalModel = payload || (selectedOption.value === "existing" ? model.value : uploadModel.value)
      const projectInfoVal = projectInfo.value || protocolInfo.value?.project

      const { protocolId, protocolUid, protocolName, projectId, projectUid, labUid } = finalModel as FormModel
      const targetProjectUUID = projectId || projectInfoVal?.id

      if (selectedOption.value === "existing") {
        if (!targetProjectUUID || !protocolId || !protocolUid || !protocolName) {
          throw new Error($t("page.hub.protocolUpload.projectRequired"))
        }

        if (mode === "reuse") {
          const response = await postReuseProtocol({
            sourceProtocolId: protocolId,
            targetProjectUUID,
            name: protocolName,
            uid: protocolUid,
          })
          if (!response)
            throw new Error("Failed to reuse protocol")

          return response
        }
        const protocolVal = protocolInfo?.value

        if (!protocolVal) {
          throw new Error("Protocol info is required")
        }
        const data = await postForkProtocol({
          protocolName,
          protocolUid,
          parentProtocolId: protocolId,
          projectId: targetProjectUUID,
        })
        if (!data)
          throw new Error("Failed to fork protocol")
        return data
      }

      const { fileList, tomlContent, envFileInclusion, envFileContent } = finalModel as UploadModel
      const fileInfo = fileList[0]

      // Get list of files to exclude based on user selection
      const filesToExclude = envFileInclusion
        ? Object.entries(envFileInclusion)
          .filter(([_, include]) => !include)
          .map(([fileName, _]) => fileName)
        : []

      const { items = [], root = "" } = packageContent.value?.content || {}
      // Filter out environment files based on user selection

      let filteredItems: ZipItem[] = [...items]
      let updated = packageContent.value?.updated || false
      let envVar: string = ""

      if (envFileContent) {
        Object.entries(envFileContent).forEach(([envPath, content]) => {
          const targetIndex = items.findIndex(({ path }) => path === envPath)
          const contentBuffer = encoder.encode(content)
          if (targetIndex === -1) {
            updated = true
            const name = envPath.split("/").pop() || envPath
            // Keep .env file and it will be removed after uploaded in server side
            if (name === ".env") {
              envVar = content
              return
            }

            filteredItems.push({
              name,
              content: contentBuffer,
              path: envPath,
              isDirectory: false,
              size: contentBuffer.length,
              lastModified: new Date(),
              compression: 0,
              originalSize: contentBuffer.length,
            })
          }
          else {
            const target = filteredItems[targetIndex]
            if (target.name === ".env") {
              envVar = content
              return
            }
            if (!compareBuffer(target.content, contentBuffer)) {
              updated = true
              filteredItems[targetIndex] = { ...target, content: contentBuffer }
            }
          }
        })
      }

      filteredItems = filterEnvFiles(filteredItems, filesToExclude)

      let protocolPackage: File | null = null
      const defaultZipData: Zippable = Object.fromEntries(filteredItems.map((item) => {
        return [item.path, item.content || new Uint8Array(0)]
      }))

      async function contentToZip(zipData: Zippable = defaultZipData) {
        const zip = await zipToPromise(zipData, { level: 0 })
        const zipname = root?.endsWith("/") ? root.slice(0, -1) : root
        protocolPackage = new File([zip], `${zipname}.zip`, { type: "application/zip" })
      }

      if (tomlContent && tomlContent !== protocolData.value?.toml_config) {
        await contentToZip({ ...defaultZipData, [`${root}protocol.toml`]: encoder.encode(tomlContent) })
      }
      else if (updated) {
        await contentToZip()
      }
      else {
        protocolPackage = fileInfo.file || null
      }

      if (!protocolPackage)
        throw new Error("File is required")

      if (!targetProjectUUID)
        throw new Error($t("page.hub.protocolUpload.projectRequired"))

      const response = await postUploadProtocol({
        file: protocolPackage,
        projectId: targetProjectUUID,
        protocolId: protocolInfo.value?.id,
        env: envVar,
      })

      if (response?.data) {
        return { project_uid: projectUid || undefined, lab_uid: labUid || undefined, ...response.data }
      }

      return response?.data
    }

    return {
      mode,
      activeModel,
      currentStep,
      stepStatus,
      selectedOption,
      isApplying,
      model,
      uploadModel,
      protocolData,
      applyResult,
      isStepValid,
      applyProtocol,
      packageContent,
      protocolInfo,
      projectInfo,
    }
  },
)

function useApplyProtocol(): ApplyProtocolState {
  const state = _useApplyProtocol()
  if (!state)
    throw new Error("useApplyProtocol must be used after useProvideApplyProtocol")
  return state
}

function useOrProvideApplyProtocol(payload?: { mode?: "fork" | "reuse", routeQuery?: boolean, defaultType?: ApplyOption | null, defaultStep?: number }) {
  try {
    return useApplyProtocol()
  }
  catch (e) {
    const { mode, routeQuery, defaultStep, defaultType } = payload || {}

    return useProvideApplyProtocol(mode, routeQuery, defaultType, defaultStep)
  }
}
export { useApplyProtocol, useOrProvideApplyProtocol, useProvideApplyProtocol }

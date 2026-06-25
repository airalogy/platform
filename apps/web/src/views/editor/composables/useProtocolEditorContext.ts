import type { ProtocolModels } from "@airalogy/shared/types"
import type { Ref } from "vue"
import type { RouteLocationNormalizedLoaded } from "vue-router"
import { getProjectInfo } from "@/service/api/projects"
import { createInjectionState } from "@vueuse/core"
import { computed, ref, watch } from "vue"

/**
 * Protocol Editor Context
 *
 * Manages the project and protocol context for the editor, including:
 * - Lab and project information from URL params
 * - Full project details (including UUID) fetched from API
 * - Protocol information (for editing existing protocols)
 * - Automatic initialization of uploadModel with correct project data
 */

export interface ProtocolEditorContext {
  // Raw URL params
  labUid: Readonly<Ref<string | null>>
  projectUid: Readonly<Ref<string | null>>
  protocolUid: Readonly<Ref<string | null>>
  protocolVersion: Readonly<Ref<string | null>>

  // Fetched data
  projectInfo: Readonly<Ref<Api.Project.MyProjectInfo | null>>
  protocolInfo: Readonly<Ref<Readonly<ProtocolModels.ProjectProtocolInfo> | null>>

  // Loading states
  isLoadingProject: Readonly<Ref<boolean>>
  isLoadingProtocol: Readonly<Ref<boolean>>

  // Computed
  isReady: Readonly<Ref<boolean>>
  projectId: Readonly<Ref<string | null>> // UUID

  // Methods
  setProtocolInfo: (info: ProtocolModels.ProjectProtocolInfo | null) => void
  refresh: () => Promise<void>
}

const [useProvideProtocolEditorContext, _useProtocolEditorContext] = createInjectionState(
  (route: RouteLocationNormalizedLoaded): ProtocolEditorContext => {
    // Extract URL params
    const labUid = ref<string | null>(null)
    const projectUid = ref<string | null>(null)
    const protocolUid = ref<string | null>(null)
    const protocolVersion = ref<string | null>(null)

    // Fetched data
    const projectInfo = ref<Api.Project.MyProjectInfo | null>(null)
    const protocolInfo = ref<ProtocolModels.ProjectProtocolInfo | null>(null)

    // Loading states
    const isLoadingProject = ref(false)
    const isLoadingProtocol = ref(false)

    // Computed
    const isReady = computed(() => {
      // If we have labUid and projectUid, we need projectInfo to be loaded
      if (labUid.value && projectUid.value) {
        return !isLoadingProject.value && projectInfo.value !== null
      }
      // If no labUid/projectUid, we're ready immediately
      return true
    })

    const projectId = computed(() => projectInfo.value?.id || null)

    // Extract params from route
    function extractParams() {
      const params = route.params as {
        labUid?: string
        projectUid?: string
        protocolUid?: string
        protocolVersion?: string
      }

      labUid.value = params.labUid || null
      projectUid.value = params.projectUid || null
      protocolUid.value = params.protocolUid || null
      protocolVersion.value = params.protocolVersion || null
    }

    // Fetch project info from API
    async function fetchProjectInfo() {
      if (!labUid.value || !projectUid.value) {
        projectInfo.value = null
        return
      }

      isLoadingProject.value = true
      try {
        const info = await getProjectInfo({
          labUid: labUid.value,
          projectUid: projectUid.value,
        })
        projectInfo.value = info
      }
      catch (e) {
        console.error("[ProtocolEditorContext] Error fetching project info:", e)
        projectInfo.value = null
      }
      finally {
        isLoadingProject.value = false
      }
    }

    // Initialize
    extractParams()

    // Watch route changes
    watch(
      () => [route.params.labUid, route.params.projectUid] as const,
      ([newLabUid, newProjectUid]) => {
        labUid.value = (newLabUid as string) || null
        projectUid.value = (newProjectUid as string) || null

        // Auto-fetch project info when params change
        if (labUid.value && projectUid.value) {
          fetchProjectInfo()
        }
        else {
          projectInfo.value = null
        }
      },
      { immediate: true },
    )

    // Methods
    function setProtocolInfo(info: ProtocolModels.ProjectProtocolInfo | null) {
      protocolInfo.value = info
    }

    async function refresh() {
      await fetchProjectInfo()
    }

    return {
      labUid: readonly(labUid),
      projectUid: readonly(projectUid),
      protocolUid: readonly(protocolUid),
      protocolVersion: readonly(protocolVersion),
      projectInfo: readonly(projectInfo),
      protocolInfo: readonly(protocolInfo) as Readonly<Ref<Readonly<ProtocolModels.ProjectProtocolInfo> | null>>,
      isLoadingProject: readonly(isLoadingProject),
      isLoadingProtocol: readonly(isLoadingProtocol),
      isReady: readonly(isReady),
      projectId: readonly(projectId),
      setProtocolInfo,
      refresh,
    }
  },
)

function useProtocolEditorContext(): ProtocolEditorContext {
  const context = _useProtocolEditorContext()
  if (!context) {
    throw new Error(
      "useProtocolEditorContext must be used within a component tree where useProvideProtocolEditorContext was called",
    )
  }
  return context
}

/**
 * Use or provide the editor context
 * If context exists, return it; otherwise create a new one
 */
function useOrProvideProtocolEditorContext(route?: RouteLocationNormalizedLoaded): ProtocolEditorContext {
  try {
    return useProtocolEditorContext()
  }
  catch {
    if (!route) {
      throw new Error("route is required when providing context for the first time")
    }
    return useProvideProtocolEditorContext(route)
  }
}

export {
  useOrProvideProtocolEditorContext,
  useProtocolEditorContext,
  useProvideProtocolEditorContext,
}

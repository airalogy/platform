import type { ComputedRef, Ref } from "vue"
import { LabRole, ProjectRole } from "@/enum"
import { getProjectInfo, getProjectInfoById } from "@/service/api/projects"
import { createInjectionState } from "@vueuse/core"

export interface ProjectInfoState {
  projectInfo: Ref<Api.Project.MyProjectInfo | null>
  fetchProjectInfo: (payload: { labUid: string, projectUid: string }) => Promise<Api.Project.MyProjectInfo | null>
  fetchProjectInfoById: (projectId: string, cb?: (...args: any[]) => any,) => Promise<Api.Project.MyProjectInfo | null>
  hasPermission: ComputedRef<boolean>
  isLoading: Ref<boolean>
  error: Ref<unknown>
  refetchProjectInfo: (delay: number, payload: { labUid: string, projectUid: string }) => Promise<Api.Project.MyProjectInfo | null>
}

const [useProvideProjectInfoStore, _useProjectInfoStore] = createInjectionState(
  (initialValue: Api.Project.MyProjectInfo | null): ProjectInfoState => {
    const {
      state: projectInfo,
      isLoading,
      error,
      execute: refetchProjectInfo,
    } = useAsyncState(fetchProjectInfo, initialValue, {
      immediate: false,
      resetOnExecute: false,
    })

    async function fetchProjectInfo(
      payload: { labUid: string, projectUid: string },
    ): Promise<Api.Project.MyProjectInfo | null> {
      const { labUid, projectUid } = payload
      if (!labUid || !projectUid) {
        return null
      }

      try {
        const data = await getProjectInfo({ labUid, projectUid })
        if (data) {
          return data
        }

        return null
      }
      catch (e) {
        return null
      }
    }

    async function fetchProjectInfoById(projectId: string, cb?: (...args: any[]) => any): Promise<Api.Project.MyProjectInfo | null> {
      if (!projectId) {
        return null
      }

      try {
        const data = await getProjectInfoById(projectId)
        if (data) {
          projectInfo.value = data
        }
        else {
          if (cb) {
            await cb()
          }
        }

        return data
      }
      catch (e) {
        if (cb) {
          await cb()
        }
        return null
      }
    }

    const hasPermission = computed(() => {
      return projectInfo.value?.user_lab_role === LabRole.OWNER || projectInfo.value?.user_lab_role === LabRole.MANAGER || projectInfo.value?.user_role === ProjectRole.MANAGER
    })

    return { projectInfo, fetchProjectInfo, fetchProjectInfoById, hasPermission, isLoading, error, refetchProjectInfo }
  },
)

function useProjectInfoStore(): ProjectInfoState {
  const state = _useProjectInfoStore()
  if (!state)
    throw new Error("useProjectInfoStore must be used after useProvideProjectInfoStore")
  return state
}
function useOrProvideProjectInfoStore(initialValue: Api.Project.MyProjectInfo | null) {
  try {
    return useProjectInfoStore()
  }
  catch (e) {
    // No parent provider found, create a new one
    return useProvideProjectInfoStore(initialValue)
  }
}

export { useOrProvideProjectInfoStore, useProjectInfoStore, useProvideProjectInfoStore }

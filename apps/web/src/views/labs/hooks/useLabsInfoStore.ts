import { LabRole } from "@/enum"
import { getLabInfo, getLabInfoByUid } from "@/service/api/labs"
import { useAuthStore } from "@/store/modules/auth"
import { createInjectionState } from "@vueuse/core"
import { computed, type ComputedRef, ref, type Ref } from "vue"

const [useProvideLabInfoStore, _useLabInfoStore] = createInjectionState(
  (initialValue: Api.Lab.LabInfo | null): LabInfoState => {
    const labInfo = ref<Api.Lab.LabInfo | null>(initialValue)
    const loading = ref(false)
    const { userInfo } = useAuthStore()

    const fetchLabInfoById = async (
      labId: string,
      cb?: (...args: any[]) => any,
    ): Promise<Api.Lab.LabInfo | null> => {
      if (!labId) {
        return null
      }
      loading.value = true
      try {
        const { data } = await getLabInfo(labId)

        if (data && data.data) {
          labInfo.value = data.data
          return data.data
        }
        return null
      }
      catch (err) {
        if (cb) {
          await cb(err)
        }
        return null
      }
      finally {
        loading.value = false
      }
    }
    const fetchLabInfoByUid = async (
      labUid: string,
      cb?: (...args: any[]) => any,
    ): Promise<Api.Lab.LabInfo | null> => {
      if (!labUid || loading.value) {
        return null
      }
      loading.value = true
      try {
        const { data } = await getLabInfoByUid(labUid)

        if (data && data.data) {
          labInfo.value = data.data
          return data.data
        }
        return null
      }
      catch (err) {
        if (cb) {
          await cb(err)
        }
        return null
      }
      finally {
        loading.value = false
      }
    }

    const userLabRole = computed(() => {
      const target = labInfo.value?.users?.find(({ id }) => id === userInfo.id)
      return target?.lab_role
    })

    const isManager = computed(() => {
      return userLabRole.value === LabRole.OWNER || userLabRole.value === LabRole.MANAGER
    })

    return { labInfo, userLabRole, isManager, fetchLabInfoById, fetchLabInfoByUid, loading }
  },
)

interface LabInfoState {
  labInfo: Ref<Api.Lab.LabInfo | null>
  userLabRole: ComputedRef<Api.Lab.LabRole>
  isManager: ComputedRef<boolean>
  fetchLabInfoById: (labId: string, cb?: (...args: any[]) => any) => Promise<Api.Lab.LabInfo | null>
  fetchLabInfoByUid: (labUid: string, cb?: (...args: any[]) => any) => Promise<Api.Lab.LabInfo | null>
  loading: Ref<boolean>
}

function useLabInfoStore(): LabInfoState {
  const state = _useLabInfoStore()
  if (!state)
    throw new Error("useLabInfoStore must be used after useProvideLabInfoStore")
  return state
}
function useOrProvideLabInfoStore(initialValue: Api.Lab.LabInfo | null) {
  try {
    return useLabInfoStore()
  }
  catch (e) {
    console.error(e)
    return useProvideLabInfoStore(initialValue)
  }
}

export { useLabInfoStore, useOrProvideLabInfoStore, useProvideLabInfoStore }

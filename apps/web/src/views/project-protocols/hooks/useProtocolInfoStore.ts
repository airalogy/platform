import type { ProtocolModels } from "@airalogy/shared/types"
import { useBoolean } from "@/composables"
import { getProtocolInfo, getProtocolInfoByUid } from "@/service/api/project-protocols"
import { getAiralogyId } from "@airalogy/shared/utils"
import { createInjectionState } from "@vueuse/core"
// useCounterStore.ts
import { computed, ref } from "vue"

const [useProvideProtocolInfoStore, useProtocolInfoStore] = createInjectionState(
  (initialValue: ProtocolModels.ProjectProtocolInfo | null) => {
    // state
    const protocolInfo = ref<ProtocolModels.ProjectProtocolInfo | null>(initialValue)

    const { bool: isLoading, setTrue: setIsLoading, setFalse: setIsLoadingFalse } = useBoolean(false)
    const memoizedGetProtocolInfoByUid = useMemoize(getProtocolInfoByUid)
    const memoizedGetProtocolInfo = useMemoize(getProtocolInfo)

    const protocolUid = computed(() => {
      if (!protocolInfo.value) {
        return null
      }

      const { airalogy_id } = protocolInfo.value

      const match = airalogy_id.match(/^airalogy\.id\.lab\..+\.project\..+\.protocol\.(.+)$/)
      if (!match) {
        return null
      }

      return match[1]
    })

    const protocolId = computed(() => {
      if (!protocolInfo.value) {
        return null
      }

      const { id } = protocolInfo.value
      return id
    })

    const airalogyId = computed(() => {
      return getAiralogyId(protocolInfo.value)
    })

    const fetchProtocolInfoByUid = async (payload: { labUid: string, projectUid: string, protocolUid: string, version?: string }, showError = true, memoize = true) => {
      const { labUid, projectUid, protocolUid, version } = payload
      if (!labUid || !projectUid || !protocolUid || isLoading.value) {
        return null
      }

      try {
        setIsLoading()
        const { data } = await (memoize ? memoizedGetProtocolInfoByUid : getProtocolInfoByUid)({ labUid, projectUid, protocolUid, version }, showError)
        if (data) {
          protocolInfo.value = data
          return data
        }

        return null
      }
      finally {
        setIsLoadingFalse()
      }
    }

    const fetchProtocolInfo = async (protocolId: string, version?: string, cb?: (...args: any[]) => any, memoize = true) => {
      if (!protocolId || isLoading.value) {
        return null
      }

      try {
        setIsLoading()
        const { data, error } = await (memoize ? memoizedGetProtocolInfo : getProtocolInfo)(protocolId, version)

        if (data) {
          protocolInfo.value = data as ProtocolModels.ProjectProtocolInfo
        }
        else {
          if (typeof cb === "function") {
            await cb()
          }
          return null
        }
        return data
      }
      finally {
        setIsLoadingFalse()
      }
    }

    return { protocolInfo, protocolUid, protocolId, fetchProtocolInfo, fetchProtocolInfoByUid, airalogyId, memoizedGetProtocolInfoByUid, memoizedGetProtocolInfo, isLoading, setIsLoading, setIsLoadingFalse }
  },
)

export { useProtocolInfoStore, useProvideProtocolInfoStore }

export function useProtocolInfoStoreWithDefaultValue() {
  return (
    useProtocolInfoStore() ?? {
      protocolInfo: ref(null),
    }
  )
}
export function useOrProvideProtocolInfoStore(initialValue: ProtocolModels.ProjectProtocolInfo | null) {
  try {
    const store = useProtocolInfoStore() as ReturnType<typeof useProvideProtocolInfoStore>
    if (!store) {
      throw new Error("Please call `useProvideProtocolInfoStore` on the appropriate parent component")
    }
    return store
  }
  catch (error) {
    return useProvideProtocolInfoStore(initialValue)
  }
}

import { getGroupsInfo } from "@/service/api/groups"
import { createInjectionState } from "@vueuse/core"
import { ref } from "vue"

const [useProvideGroupInfoStore, useGroupInfoStore] = createInjectionState(
  (initialValue: Api.Groups.MyGroupsInfo | null) => {
    // state
    const groupInfo = ref<Api.Groups.MyGroupsInfo | null>(initialValue)

    // getters

    // actions

    const fetchGroupInfo = async (
      groupId: string,
      cb: (...args: any[]) => any,
    ): Promise<Api.Groups.MyGroupsInfo | null> => {
      if (!groupId) {
        return null
      }

      try {
        const { data } = await getGroupsInfo(groupId)

        if (data && data.data) {
          groupInfo.value = data.data
          return data.data
        }
        return null
      }
      catch (err) {
        await cb(err)
        return null
      }
    }

    return { groupInfo, fetchGroupInfo }
  },
)

export { useProvideGroupInfoStore }
export { useGroupInfoStore }

export function useGroupInfoStoreWithDefaultValue() {
  return (
    useGroupInfoStore() ?? {
      groupInfo: null,
    }
  )
}

export function useGroupInfoStoreOrThrow() {
  const counterStore = useGroupInfoStore()
  if (!counterStore)
    throw new Error("Please call `useProvideCounterStore` on the appropriate parent component")

  return counterStore
}

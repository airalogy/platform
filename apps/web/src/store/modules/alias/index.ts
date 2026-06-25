import type { Alias, UserAliases } from "@/types/store/alias"
import { SetupStoreId } from "@/enum"
// import { getUserAliases } from "@/service/api/users"
import { defineStore } from "pinia"
import { ref } from "vue"

export const useAliasStore = defineStore(SetupStoreId.ALIAS, () => {
  const aliases = ref<UserAliases>({})

  async function fetchUserAliases(userId: string) {
    if (aliases.value[userId])
      return

    // TODO: Implement getUserAliases API endpoint
    // const { data } = await getUserAliases(userId)
    // if (data) {
    //   aliases.value[userId] = data
    // }
  }

  function getPrioritizedAlias(userId: string): Alias[] | undefined {
    const userAliases = aliases.value[userId]
    if (!userAliases || userAliases.length === 0) {
      return undefined
    }

    const sortedAliases = [...userAliases].sort((a, b) => a.priority - b.priority)
    return sortedAliases
  }

  return {
    aliases,
    fetchUserAliases,
    getPrioritizedAlias,
  }
})

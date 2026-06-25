import { useAliasStore } from "@/store/modules/alias"
import { computed } from "vue"

export function useUserAlias(userId: string) {
  const aliasStore = useAliasStore()

  aliasStore.fetchUserAliases(userId)

  const prioritizedAlias = computed(() => {
    return aliasStore.getPrioritizedAlias(userId)
  })

  return {
    prioritizedAlias,
  }
}

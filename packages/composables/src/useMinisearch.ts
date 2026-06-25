import MiniSearch, { type Options as MiniSearchOptions } from "minisearch"
import { ref, shallowRef } from "vue"

export function useMinisearch<T>(options: { fallback: T[], options: MiniSearchOptions }) {
  const { fallback, options: searchOptions } = options
  const minisearch = shallowRef(new MiniSearch(searchOptions))

  const fallbackResults = shallowRef<Record<string, T[]>>({ all: fallback })

  const minisearches = shallowRef<Record<string, MiniSearch<T>>>({ all: minisearch.value })

  const loaded = ref(false)

  function setMinisearch(provider: string, minisearch: MiniSearch<T>) {
    minisearches.value[provider] = minisearch
  }

  function setFallbackResults(provider: string, results: T[]) {
    fallbackResults.value[provider] = results
  }

  function setLoaded(value: boolean) {
    loaded.value = value
  }

  function resetStore() {
    minisearches.value = {}
    fallbackResults.value = {}
    loaded.value = false
  }

  return {
    minisearches,
    fallbackResults,
    loaded,
    setMinisearch,
    setFallbackResults,
    setLoaded,
    resetStore,
  }
}

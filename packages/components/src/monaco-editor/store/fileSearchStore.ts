import type { MatchResult, TreeMatchResult } from "../utils/match"
import { defineStore } from "pinia"
import { computed, ref } from "vue"

export interface SearchBaseOptions {
  caseSensitive: boolean
  wholeWord: boolean
  regex: boolean
}

export interface ReplaceOptions {
  preserveCase: boolean
}

export interface FilterOptions {
  isUsed: boolean
  isOnlyOpened: boolean
  isUseGitignoreFile: boolean
}

export interface SearchOptions extends Required<SearchBaseOptions & ReplaceOptions & FilterOptions> {
  [key: string]: any
}

export const useFileSearchStore = defineStore("file-search", () => {
  // State
  const searchInpVal = ref("")
  const searchBaseOptions = ref<SearchBaseOptions>({
    caseSensitive: false,
    wholeWord: false,
    regex: false,
  })
  const searchResult = ref<MatchResult[]>([])
  const searchResultTree = ref<TreeMatchResult[]>([])

  // Actions
  function setSearchInpVal(value: string) {
    searchInpVal.value = value
  }

  function setSearchResult(results: MatchResult[]) {
    searchResult.value = results
  }

  function setSearchResultTree(results: TreeMatchResult[]) {
    searchResultTree.value = results
  }

  function setSearchBaseOptionItem(key: keyof SearchBaseOptions) {
    searchBaseOptions.value[key] = !searchBaseOptions.value[key]
  }

  function clearResultAndSearchInpval() {
    searchResult.value = []
    searchInpVal.value = ""
  }

  return {
    // State
    searchInpVal,
    searchBaseOptions,
    searchResult,
    searchResultTree,
    // Actions
    setSearchInpVal,
    setSearchResult,
    setSearchResultTree,
    setSearchBaseOptionItem,
    clearResultAndSearchInpval,
  }
})

export const useFileReplaceStore = defineStore("file-replace", () => {
  // State
  const replaceInpVal = ref("")
  const replaceOptions = ref<ReplaceOptions>({
    preserveCase: false,
  })

  // Actions
  function setReplaceInpVal(value: string) {
    replaceInpVal.value = value
  }

  function setReplaceOptionItem(key: keyof ReplaceOptions) {
    replaceOptions.value[key] = !replaceOptions.value[key]
  }

  return {
    // State
    replaceInpVal,
    replaceOptions,
    // Actions
    setReplaceInpVal,
    setReplaceOptionItem,
  }
})

export const useFileFilterStore = defineStore("file-filter", () => {
  // State
  const includeFileInpVal = ref("")
  const excludeFileInpVal = ref("")
  const filterSearchOptions = ref<FilterOptions>({
    isUsed: false,
    isOnlyOpened: false,
    isUseGitignoreFile: true,
  })

  // Actions
  function setIncludeFileInpVal(value: string) {
    includeFileInpVal.value = value
  }

  function setExcludeFileInpVal(value: string) {
    excludeFileInpVal.value = value
  }

  function setFilterSearchOptionItem(key: keyof FilterOptions) {
    filterSearchOptions.value[key] = !filterSearchOptions.value[key]
  }

  // Computed
  const includeFiles = computed(() => includeFileInpVal.value.split(",").filter(Boolean))
  const excludeFiles = computed(() => excludeFileInpVal.value.split(",").filter(Boolean))
  const filters = computed(() => ({
    includeFiles: includeFiles.value,
    excludeFiles: excludeFiles.value,
  }))

  return {
    // State
    includeFileInpVal,
    excludeFileInpVal,
    filterSearchOptions,
    // Computed
    includeFiles,
    excludeFiles,
    filters,
    // Actions
    setIncludeFileInpVal,
    setExcludeFileInpVal,
    setFilterSearchOptionItem,
  }
})

export const useSearchHeaderStore = defineStore("search-header", () => {
  // State
  const viewMode = ref<"tree" | "list">("list")

  // Actions
  function setViewMode(mode: "tree" | "list") {
    viewMode.value = mode
  }

  return {
    viewMode,
    setViewMode,
  }
})

import type { GlobalThemeOverrides } from "naive-ui"
import type { _ExtractActionsFromSetupStore, _ExtractGettersFromSetupStore, _ExtractStateFromSetupStore, StoreDefinition } from "pinia"
import type { PiniaStore } from "../../../shared/src"
import { useEventListener } from "@vueuse/core"
import { defineStore, storeToRefs } from "pinia"
import { computed, type ComputedRef, effectScope, onScopeDispose, ref, type Ref, type ShallowRef, toRefs, watch } from "vue"
import { SetupStoreId } from "../enum/store"
import { defaultThemeSettings } from "./constants"
import {
  addThemeVarsToGlobal,
  createThemeToken,
  getNaiveTheme,
  toggleCssDarkMode,
} from "./shared"

interface ThemeStoreSetup {
  themeScheme: Ref<Theme.ThemeSetting["themeScheme"]>
  themeColor: Ref<Theme.ThemeSetting["themeColor"]>
  otherColor: Ref<Theme.ThemeSetting["otherColor"]>
  isInfoFollowPrimary: Ref<Theme.ThemeSetting["isInfoFollowPrimary"]>
  layout: Ref<Theme.ThemeSetting["layout"]>
  page: Ref<Theme.ThemeSetting["page"]>
  header: Ref<Theme.ThemeSetting["header"]>
  tab: Ref<Theme.ThemeSetting["tab"]>
  fixedHeaderAndTab: Ref<Theme.ThemeSetting["fixedHeaderAndTab"]>
  sider: Ref<Theme.ThemeSetting["sider"]>
  footer: Ref<Theme.ThemeSetting["footer"]>
  tokens: Ref<Theme.ThemeSetting["tokens"]>
  content: Ref<Theme.ThemeSetting["content"]>
  themeOverrides: Ref<GlobalThemeOverrides>
  darkMode: ComputedRef<boolean>
  themeColors: ComputedRef<Theme.ThemeColor>
  naiveTheme: ComputedRef<GlobalThemeOverrides>
  resetStore: () => void
  toggleThemeScheme: () => void
  updateThemeColors: (key: Theme.ThemeColorKey, color: string) => void
  setThemeLayout: (mode: Theme.ThemeLayoutMode) => void
  setupThemeVarsToGlobal: () => void
  callback: ShallowRef<Record<string, (...args: any[]) => void>>
  cacheThemeSettings: ShallowRef<(settings: Theme.ThemeSetting) => void>
}

function createThemeStore(): ThemeStoreSetup {
  // osTheme is no longer used (dark mode removed)

  /** Theme settings */
  const settings = ref<Theme.ThemeSetting>({
    ...defaultThemeSettings,
  })

  // Simplified: only light theme is supported
  const themeOverrides = ref<GlobalThemeOverrides>({})

  const cacheThemeSettings = shallowRef<(settings: Theme.ThemeSetting) => void>(() => {})
  const callback = shallowRef<Record<string, (...args: any[]) => void>>({})

  /** Dark mode (DEPRECATED - always returns false, dark mode has been removed) */
  const darkMode = computed(() => {
    // Dark mode has been removed from the project
    // This computed property is kept for backward compatibility but always returns false
    return false
  })

  /** Theme colors */
  const themeColors = computed(() => {
    const { themeColor, otherColor, isInfoFollowPrimary } = settings.value
    const colors: Theme.ThemeColor = {
      primary: themeColor,
      ...otherColor,
      info: isInfoFollowPrimary ? themeColor : otherColor.info,
    }
    return colors
  })

  /** Naive theme */
  const naiveTheme = computed(() => {
    return getNaiveTheme({
      colors: themeColors.value,
      isDarkMode: false, // Dark mode has been removed
      themeOverrides: toValue(themeOverrides),
      lightThemeOverrides: toValue(themeOverrides),
    })
  })

  /**
   * Set theme layout
   *
   * @param mode Theme layout mode
   */
  function setThemeLayout(mode: Theme.ThemeLayoutMode) {
    settings.value.layout.mode = mode
  }
  /** Reset store */
  function resetStore() {
    settings.value = {
      ...defaultThemeSettings,
    }
    themeOverrides.value = {}
    callback.value = {}
    cacheThemeSettings.value = () => {}
  }
  /** Setup theme vars to global */
  function setupThemeVarsToGlobal() {
    const { themeTokens } = createThemeToken(themeColors.value, settings.value.tokens)
    // Dark theme tokens are no longer generated
    addThemeVarsToGlobal(themeTokens)
  }

  /**
   * Toggle theme scheme (DEPRECATED - only light mode is supported)
   * @deprecated Dark mode has been removed, this function does nothing
   */
  function toggleThemeScheme() {
    // Dark mode has been removed, theme is always 'light'
    // This function is kept for backward compatibility but does nothing
  }

  /**
   * Update theme colors
   *
   * @param key Theme color key
   * @param color Theme color
   */
  function updateThemeColors(key: Theme.ThemeColorKey, color: string) {
    if (key === "primary") {
      settings.value.themeColor = color
    }
    else {
      settings.value.otherColor[key] = color
    }
  }

  const scope = effectScope()
  // cache theme settings when page is closed or refreshed
  useEventListener(window, "beforeunload", () => {
    const fn = toValue(cacheThemeSettings)
    if (fn) {
      fn(settings.value)
    }
  })

  // watch store
  scope.run(() => {
    // Dark mode watch has been removed (dark mode functionality removed)
    // Initialize with light mode
    toggleCssDarkMode(false)

    // themeColors change, update css vars and storage theme color
    watch(
      themeColors,
      (val) => {
        setupThemeVarsToGlobal()

        const fn = callback.value.themeColors

        if (fn) {
          fn(val)
        }
      },
      { immediate: true },
    )
  })

  /** On scope dispose */
  onScopeDispose(() => {
    scope.stop()
  })

  return {
    ...toRefs(settings.value),
    themeOverrides,
    darkMode,
    themeColors,
    naiveTheme,
    resetStore,
    toggleThemeScheme,
    updateThemeColors,
    setThemeLayout,
    setupThemeVarsToGlobal,
    callback,
    cacheThemeSettings,
  }
}

export const useThemeStore: StoreDefinition<
  SetupStoreId.Theme,
  _ExtractStateFromSetupStore<ThemeStoreSetup>,
  _ExtractGettersFromSetupStore<ThemeStoreSetup>,
  _ExtractActionsFromSetupStore<ThemeStoreSetup>
> = defineStore(SetupStoreId.Theme, createThemeStore)

/** Theme store */
export function setupThemeStore(configs: {
  settings?: Theme.ThemeSetting
  tokens?: Theme.ThemeSetting["tokens"]
  themeOverrides?: GlobalThemeOverrides | null
  darkThemeOverrides?: GlobalThemeOverrides | null
  lightThemeOverrides?: GlobalThemeOverrides | null
  cacheThemeSettings?: (settings: Theme.ThemeSetting) => void
  callback?: Record<string, (...args: any[]) => void>
}) {
  const { settings: defaultSettings, tokens: defaultTokens, callback: defaultCallback, cacheThemeSettings: defaultCacheFn, themeOverrides: defaultThemeOverrides, lightThemeOverrides: _defaultLightThemeOverrides, darkThemeOverrides: _defaultDarkThemeOverrides } = configs

  const store = useThemeStore()
  const { tokens, callback, cacheThemeSettings, themeOverrides, ...settings } = storeToRefs(store)

  if (defaultSettings) {
    Object.entries(defaultSettings).forEach(([key, val]) => {
    // @ts-expect-error settings is a Theme.ThemeSetting
      const settingRef = settings[key]
      if (settingRef) {
        settingRef.value = val
      }
    })
  }

  if (defaultTokens) {
    tokens.value = defaultTokens
  }

  if (defaultCallback) {
    Object.assign(callback.value, defaultCallback)
  }

  if (defaultCacheFn) {
    cacheThemeSettings.value = defaultCacheFn
  }

  if (defaultThemeOverrides) {
    themeOverrides.value = defaultThemeOverrides
  }

  // lightThemeOverrides and darkThemeOverrides are ignored (dark mode removed)

  return store
}

export type ThemeStore = PiniaStore<typeof useThemeStore>

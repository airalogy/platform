import type { VueRenderer } from "@tiptap/vue-3"
import type { _ExtractActionsFromSetupStore, _ExtractGettersFromSetupStore, _ExtractStateFromSetupStore, StoreDefinition } from "pinia"
import { useBasicLayout, useBoolean } from "@/composables"
import { SetupStoreId } from "@/enum"
import { $t, DEFAULT_LOCALE, LOCALE_OPTIONS, setLocale } from "@/locales"
import { setDayjsLocale } from "@/locales/dayjs"
import { router } from "@/router"
import { localStg } from "@/utils/storage"
import { useFloating } from "@floating-ui/vue"
import { useTitle } from "@vueuse/core"
import { defineStore } from "pinia"
import { effectScope, onScopeDispose, ref, type Ref, type StyleValue, type VNode, watch } from "vue"
import { useRouteStore } from "../route"
import { useTabStore } from "../tab"

interface AppPopoverComponent {
  renderedComponent?: {
    vNode?: VNode | null
  }
}

interface AppStoreSetup {
  isMobile: Ref<boolean>
  reloadFlag: Ref<boolean>
  reloadPage: (duration?: number) => Promise<void>
  fullContent: Ref<boolean>
  locale: Ref<I18n.LangType>
  localeOptions: I18n.LangOption[]
  changeLocale: (lang: I18n.LangType) => void
  themeDrawerVisible: Ref<boolean>
  openThemeDrawer: () => void
  closeThemeDrawer: () => void
  toggleFullContent: () => void
  contentXScrollable: Ref<boolean>
  setContentXScrollable: (value: boolean) => void
  siderCollapse: Ref<boolean>
  setSiderCollapse: (value: boolean) => void
  toggleSiderCollapse: () => void
  mixSiderFixed: Ref<boolean>
  setMixSiderFixed: (value: boolean) => void
  toggleMixSiderFixed: () => void
  breakpoints: unknown
  isSpinWrapper: Ref<boolean>
  setIsSpinWrapper: (value: boolean) => void
  loading: Ref<boolean>
  setLoading: (value: boolean) => void
  popoverReference: Ref<HTMLElement | null>
  popoverFloating: Ref<HTMLDivElement | null>
  popoverComponent: Ref<AppPopoverComponent | null>
  floatingStyles: Readonly<Ref<StyleValue>>
  updateFloatingStyles: (...args: any[]) => unknown
}

function createAppStore(): AppStoreSetup {
  // const themeStore = useThemeStore()
  const routeStore = useRouteStore()
  const tabStore = useTabStore()
  const scope = effectScope()
  const { breakpoints, isMobile } = useBasicLayout()
  const {
    bool: themeDrawerVisible,
    setTrue: openThemeDrawer,
    setFalse: closeThemeDrawer,
  } = useBoolean()
  const { bool: reloadFlag, setBool: setReloadFlag } = useBoolean(true)
  const { bool: fullContent, toggle: toggleFullContent } = useBoolean()
  const { bool: contentXScrollable, setBool: setContentXScrollable } = useBoolean()
  const {
    bool: siderCollapse,
    setBool: setSiderCollapse,
    toggle: toggleSiderCollapse,
  } = useBoolean()
  const {
    bool: mixSiderFixed,
    setBool: setMixSiderFixed,
    toggle: toggleMixSiderFixed,
  } = useBoolean()
  const { bool: isSpinWrapper, setBool: setIsSpinWrapper } = useBoolean(false)
  const { bool: loading, setBool: setLoading } = useBoolean(false)

  /**
   * Reload page
   *
   * @param duration Duration time
   */
  async function reloadPage(duration = 0) {
    setReloadFlag(false)

    if (duration > 0) {
      await new Promise((resolve) => {
        setTimeout(resolve, duration)
      })
    }

    setReloadFlag(true)
  }

  const locale = ref<I18n.LangType>(localStg.get("lang") || DEFAULT_LOCALE)

  const localeOptions: I18n.LangOption[] = LOCALE_OPTIONS

  function changeLocale(lang: I18n.LangType) {
    locale.value = lang
    setLocale(lang)
    localStg.set("lang", lang)
  }

  /** Update document title by locale */
  function updateDocumentTitleByLocale() {
    const { i18nKey, title } = router.currentRoute.value.meta

    const documentTitle = i18nKey ? $t(i18nKey as I18n.I18nKey) : (title)

    useTitle(documentTitle)
  }

  const popoverReference = ref<HTMLElement | null>(null)
  const popoverFloating = ref<HTMLDivElement | null>(null)
  const popoverComponent = ref<VueRenderer | null>(null)

  const { floatingStyles, update: updateFloatingStyles } = useFloating(popoverReference, popoverFloating, {
    placement: "top-start",
  })

  function init() {
    setLocale(locale.value)
  }

  init()

  // watch store
  scope.run(() => {
    // watch isMobile, if is mobile, collapse sider
    watch(
      isMobile,
      (newValue) => {
        if (newValue) {
          setSiderCollapse(true)

          // themeStore.setThemeLayout("vertical")
        }
      },
      { immediate: true },
    )

    // watch locale
    watch(locale, () => {
      // update document title by locale
      updateDocumentTitleByLocale()

      // update global menus by locale
      routeStore.updateGlobalMenusByLocale()

      // update tabs by locale
      tabStore.updateTabsByLocale()

      // sey dayjs locale
      setDayjsLocale(locale.value)
    }, { immediate: true })
  })

  /** On scope dispose */
  onScopeDispose(() => {
    scope.stop()
  })

  // init already called before watchers

  return {
    isMobile,
    reloadFlag,
    reloadPage,
    fullContent,
    locale,
    localeOptions,
    changeLocale,
    themeDrawerVisible,
    openThemeDrawer,
    closeThemeDrawer,
    toggleFullContent,
    contentXScrollable,
    setContentXScrollable,
    siderCollapse,
    setSiderCollapse,
    toggleSiderCollapse,
    mixSiderFixed,
    setMixSiderFixed,
    toggleMixSiderFixed,
    breakpoints,
    isSpinWrapper,
    setIsSpinWrapper,
    loading,
    setLoading,
    popoverReference,
    popoverFloating,
    popoverComponent,
    floatingStyles,
    updateFloatingStyles,
  }
}

export const useAppStore: StoreDefinition<
  SetupStoreId.APP,
  _ExtractStateFromSetupStore<AppStoreSetup>,
  _ExtractGettersFromSetupStore<AppStoreSetup>,
  _ExtractActionsFromSetupStore<AppStoreSetup>
> = defineStore(SetupStoreId.APP, createAppStore)

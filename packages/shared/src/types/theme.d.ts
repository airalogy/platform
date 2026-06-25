/** Theme namespace */
declare namespace Theme {
  type ColorPaletteNumber = 50 | 100 | 200 | 300 | 400 | 500 | 600 | 700 | 800 | 900 | 950
  type ThemeScheme = "light" | "dark" | "auto"
  /**
   * The layout mode
   *
   * - Vertical: the vertical menu in left
   * - Horizontal: the horizontal menu in top
   * - Vertical-mix: two vertical mixed menus in left
   * - Horizontal-mix: the vertical menu in left and horizontal menu in top
   */
  type ThemeLayoutMode = "vertical" | "horizontal" | "vertical-mix" | "horizontal-mix"

  /**
   * The scroll mode when content overflow
   *
   * - Wrapper the wrapper component's root element overflow
   * - Content the content component overflow
   */
  type ThemeScrollMode = "wrapper" | "content"

  /**
   * Tab mode
   *
   * - Chrome: chrome style
   * - Button: button style
   */
  type ThemeTabMode = "button" | "chrome"

  /** Page animate mode */
  type ThemePageAnimateMode =
    | "fade"
    | "fade-slide"
    | "fade-bottom"
    | "fade-scale"
    | "zoom-fade"
    | "zoom-out"
    | "none"

  /** Theme setting */
  interface ThemeSetting {
    /** Theme scheme */
    themeScheme: ThemeScheme
    /** Theme color */
    themeColor: string
    /** Other color */
    otherColor: OtherColor
    /** Whether info color is followed by the primary color */
    isInfoFollowPrimary: boolean
    /** Layout */
    layout: {
      /** Layout mode */
      mode: ThemeLayoutMode
      /** Scroll mode */
      scrollMode: ThemeScrollMode
      /** Max width */
      maxWidth: number
    }
    /** Page */
    page: {
      /** Whether to show the page transition */
      animate: boolean
      /** Page animate mode */
      animateMode: ThemePageAnimateMode
    }
    /** Header */
    header: {
      /** Header height */
      height: number
      /** Header breadcrumb */
      breadcrumb: {
        /** Whether to show the breadcrumb */
        visible: boolean
        /** Whether to show the breadcrumb icon */
        showIcon: boolean
      }
    }
    /** Tab */
    tab: {
      /** Whether to show the tab */
      visible: boolean
      /**
       * Whether to cache the tab
       *
       * If cache, the tabs will get from the local storage when the page is refreshed
       */
      cache: boolean
      /** Tab height */
      height: number
      /** Tab mode */
      mode: ThemeTabMode
    }
    /** Fixed header and tab */
    fixedHeaderAndTab: boolean
    /** Sider */
    sider: {
      /** Inverted sider */
      inverted: boolean
      /** Sider width */
      width: number
      /** Collapsed sider width */
      collapsedWidth: number
      /** Sider width when the layout is 'vertical-mix' or 'horizontal-mix' */
      mixWidth: number
      /** Collapsed sider width when the layout is 'vertical-mix' or 'horizontal-mix' */
      mixCollapsedWidth: number
      /** Child menu width when the layout is 'vertical-mix' or 'horizontal-mix' */
      mixChildMenuWidth: number
    }
    /** Footer */
    footer: {
      /** Whether to show the footer */
      visible: boolean
      /** Whether fixed the footer */
      fixed: boolean
      /** Footer height */
      height: number
      /** Whether float the footer to the right when the layout is 'horizontal-mix' */
      right: boolean
    }
    /** Container content class */
    content: {
      /** Container content class */
      containerContentClass: string
      /** Content class */
      contentClass: string
    }

    /** define some theme settings tokens, will transform to css variables */
    tokens: {
      light: ThemeSettingToken
      dark?: {
        [K in keyof ThemeSettingToken]?: Partial<ThemeSettingToken[K]>;
      }
    }
  }

  interface OtherColor {
    info: string
    success: string
    warning: string
    error: string
  }

  interface ThemeColor extends OtherColor {
    primary: string
  }

  type ThemeColorKey = keyof ThemeColor

  type ThemePaletteColor = {
    [key in ThemeColorKey | `${ThemeColorKey}-${ColorPaletteNumber}`]: string
  }

  type BaseToken = Record<string, Record<string, string>>

  type ThemeSettingTokenColorKey = "nprogress" | "container" | "layout" | "inverted" | "base-text" | "text-secondary"
  type ThemeSettingTokenColor = Record<Exclude<ThemeSettingTokenColorKey, "nprogress">, string> & { nprogress?: string }

  interface ThemeSettingTokenBoxShadow {
    header: string
    sider: string
    tab: string
    [key: string]: string
  }

  /** Theme setting token */
  interface ThemeSettingToken {
    colors: ThemeSettingTokenColor & { [key: string]: string | Record<string, string> }
    boxShadow: ThemeSettingTokenBoxShadow
  }

  type ThemeTokenColor = ThemePaletteColor & ThemeSettingTokenColor

  /** Theme token CSS variables */
  interface ThemeTokenCSSVars extends BaseToken {
    colors: ThemeTokenColor
    boxShadow: ThemeSettingTokenBoxShadow
  }
}

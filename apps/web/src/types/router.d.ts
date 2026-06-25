import type { LayoutScrollMode } from "./layout"
import type { RouteNameKey } from "./page-route"
import "vue-router"

declare module "vue-router" {
  interface RouteMeta {
    /**
     * Title of the route
     *
     * It can be used in document title
     */
    title: string
    /**
     * I18n title of the route
     *
     * It's used in i18n, if it is set, the title and i18nKey will be ignored
     */
    i18nTitle?: I18n.I18nRouteKey
    /**
     * I18n key of the route
     *
     * It's used in i18n, if it is set, the title will be ignored
     */
    i18nKey?: I18n.I18nKey
    /**
     * I18n key of global breadcrumb
     *
     */
    breadcrumbI18nKey?: I18n.I18nKey
    /**
     * Roles of the route
     *
     * Route can be accessed if the current user has at least one of the roles
     */
    roles?: string[]
    /** Whether to cache the route */
    keepAlive?: boolean
    /**
     * Is constant route
     *
     * Does not need to login, and the route is defined in the front-end
     */
    constant?: boolean
    /** Whether guests can access the route without logging in */
    allowGuest?: boolean
    /**
     * Iconify icon
     *
     * It can be used in the menu or breadcrumb
     */
    icon?: string
    /**
     * Local icon
     *
     * In "src/assets/svg-icon", if it is set, the icon will be ignored
     */
    localIcon?: string
    /** Router order */
    order?: number
    /** The outer link of the route */
    href?: string
    /** Whether to hide in menu */
    hideInMenu?: boolean
    /** Whether to hide in breadcrumb */
    hideInBreadcrumb?: boolean
    /** Whether to hide global footer */
    hideFooter?: boolean
    /** Override layout scroll mode for this route */
    scrollMode?: LayoutScrollMode
    /** Disable layout content scroll (use inner scroll) */
    disableContentScroll?: boolean
    /** Force layout to fill viewport height */
    layoutFullHeight?: boolean
    /** Whether to hide in tab */
    hideInTab?: boolean
    /** Whether to show in top level menu */
    topLevel?: boolean
    /** Whether to reload the component when navigating to the same route with different params */
    reload?: boolean
    /** Whether to use spin wrapper */
    useSpinWrapper?: boolean
  }

  export type RouteRecordName = RouteNameKey

  interface RouteLocationNamedRaw {
    name: RouteNameKey
  }
  interface MatcherLocation {
    name: RouteNameKey | null | undefined
  }

  interface RouteLocationNormalizedLoaded {
    name: RouteNameKey | null | undefined
  }
}

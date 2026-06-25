/** The global namespace for the app */
declare namespace App {
  /** Global namespace */
  namespace Global {
    type VNode = import("vue").VNode
    type RouteLocationNormalizedLoaded = import("vue-router").RouteLocationNormalizedLoaded
    type RouteNameKey = import("./page-route.d.ts").RouteNameKey
    type RouteKey = RouteNameKey | "user-center" | "about"
    type TabKey = Extract<
      RouteKey,
      | "user-profile"
      | "profile-settings"
      | "profile-records"
      | "project-dashboard"
      | "project-starred"
      | "lab-records"
      | "project-protocols"
      | "project-records"
      | "project-members"
      | "project-settings"
      | "groups-my"
      | "groups-public"
      | "group-projects"
      | "protocol-protocols"
      | "protocol-records"
      | "protocol-analyses"
      | "protocol-settings"
      | "protocol-discussions"
      | "search-index"
      | "search-protocol"
      | "search-record"
      | "search-discussion"
      | "hub-detail-protocol"
      | "hub-detail-record"
      | "hub-detail-discussion"
    >
    type LastLevelRouteKey = Extract<
      RouteKey,
      | "403"
      | "404"
      | "500"
      | "login"
      | "about"
      | "function_multi-tab"
      | "function_tab"
      | "home"
      | "manage_role"
      | "manage_route"
      | "manage_user-detail"
      | "manage_user"
      | "multi-menu_first_child"
      | "multi-menu_second_child_home"
      | "user-center"
    >
    type RouteMap = Record<string, string>
    type RoutePath = string

    /** The global header props */
    interface HeaderProps {
      /** Whether to show the logo */
      showLogo?: boolean
      /** Whether to show the menu toggler */
      showMenuToggler?: boolean
      /** Whether to show the menu */
      showMenu?: boolean
    }

    /** The global menu */
    interface Menu {
      /**
       * The menu key
       *
       * Equal to the route key
       */
      key: string
      /** The menu label */
      label: string
      /** The breadcrumb label */
      breadcrumbLabel?: string

      /** The menu i18n key */
      i18nKey?: I18n.I18nKey

      /** The breadcrumb i18n key */
      breadcrumbI18nKey?: I18n.I18nKey
      /** The route key */
      routeKey: RouteKey
      /** The route path */
      routePath: RoutePath
      /** The menu icon */
      icon?: () => VNode
      /** The menu children */
      children?: Menu[]
      meta?: {
        hideInMenu?: boolean
        hideInBreadcrumb?: boolean
      }
    }

    type Breadcrumb = Partial<
      Omit<Menu, "children"> & {
        to: import("vue-router").RouteLocationRaw
        options: Breadcrumb[]
      }
    >

    /** Tab route */
    type TabRoute = Pick<RouteLocationNormalizedLoaded, "name" | "path" | "meta"> &
      Partial<Pick<RouteLocationNormalizedLoaded, "fullPath" | "query">>

    /** The global tab */
    interface Tab {
      /** The tab id */
      id: string
      /** The tab label */
      label: string
      /**
       * The new tab label
       *
       * If set, the tab label will be replaced by this value
       */
      newLabel?: string
      /**
       * The old tab label
       *
       * when reset the tab label, the tab label will be replaced by this value
       */
      oldLabel?: string
      /** The tab route key */
      routeKey: LastLevelRouteKey
      /** The tab route path */
      routePath: RouteMap[LastLevelRouteKey]
      /** The tab route full path */
      fullPath: string
      /** The tab fixed index */
      fixedIndex?: number
      /**
       * Tab icon
       *
       * Iconify icon
       */
      icon?: string
      /**
       * Tab local icon
       *
       * Local icon
       */
      localIcon?: string
      /** I18n key */
      i18nKey?: I18n.I18nKey
    }

    /** Form rule */
    type FormRule = import("naive-ui").FormItemRule

    /** The global dropdown key */
    type DropdownKey = "closeCurrent" | "closeOther" | "closeLeft" | "closeRight" | "closeAll"

    /** The global modal */
    interface Modal {
      /** The modal id */
      id: string
      /** The modal label */
      label: string
      /**
       * The new modal label
       *
       * If set, the modal label will be replaced by this value
       */
      newLabel?: string
      /**
       * The old modal label
       *
       * when reset the modal label, the tab label will be replaced by this value
       */
      oldLabel?: string
      /** The modal route key */
      routeKey: LastLevelRouteKey
      /** The modal route path */
      routePath: RouteMap[LastLevelRouteKey]
      /** The modal route full path */
      fullPath: string
      /** The modal fixed index */
      fixedIndex?: number
      /**
       * modal icon
       *
       * Iconify icon
       */
      icon?: string
      /**
       * modal local icon
       *
       * Local icon
       */
      localIcon?: string
      /** I18n key */
      i18nKey?: I18n.I18nKey
    }
  }

  /** Service namespace */
  namespace Service {
    /** The backend service env type */
    type EnvType = "dev" | "prod"

    /** Other baseURL key */
    type OtherBaseURLKey = "demo" | "minio" | "proxy-vpn"

    /** The backend service config */
    interface ServiceConfig<T extends OtherBaseURLKey = OtherBaseURLKey> {
      /** The backend service base url */
      baseURL: string
      /** Other backend service base url map */
      otherBaseURL: Partial<Record<T, string>>
    }

    /** The backend service config map */
    type ServiceConfigMap = Record<EnvType, ServiceConfig>

    /** The backend service response data */
    interface Response<T = unknown> {
      /** The backend service response code */
      code: string
      /** The backend service response message */
      msg: string
      /** The backend service response data */
      data: T
    }

    /** The demo backend service response data */
    interface DemoResponse<T = unknown> {
      /** The backend service response code */
      status: string
      /** The backend service response message */
      message: string
      /** The backend service response data */
      result: T
    }
  }
}

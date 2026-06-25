import type { _RouteRecordBase } from "vue-router"

export namespace Route {
  export type ConstRoute = Omit<_RouteRecordBase, "name" | "path" | "children"> & {
    name: string
    path: string
    component?: string
    children?: ConstRoute[]
    meta?: {
      title?: string
      i18nTitle?: string
      icon?: string
      order?: number
      roles?: string[]
      requiresAuth?: boolean
      keepAlive?: boolean
      multiTab?: boolean
      hide?: boolean
    }
  }

  export interface MenuRoute extends ConstRoute {
    id: string
  }

  export interface UserRoute {
    routes: MenuRoute[]
    home: string
  }

  export interface RouteModule {
    path: string
    component?: string | (() => Promise<any>)
    children?: RouteModule[]
    name?: string
    alias?: string | string[]
    redirect?: string
    meta?: ConstRoute["meta"]
  }
}

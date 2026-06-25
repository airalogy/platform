declare namespace Api {
  namespace Tab {
    interface TabRoute {
      name: string
      path: string
      meta?: {
        title?: string
        i18nTitle?: string
        icon?: string
        keepAlive?: boolean
        multiTab?: boolean
      }
    }

    interface Tab {
      id: string
      title: string
      path: string
      name: string
      fullPath: string
      meta?: TabRoute["meta"]
    }
  }
}

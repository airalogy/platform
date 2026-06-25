interface Window {
  /** NProgress instance */
  NProgress?: import("nprogress").NProgress
  /** Loading bar instance */
  $loadingBar?: import("naive-ui").LoadingBarProviderInst
  /** Dialog instance */
  $dialog?: import("naive-ui").DialogProviderInst
  /** Message instance */
  $message?: import("naive-ui").MessageProviderInst
  /** Notification instance */
  $notification?: import("naive-ui").NotificationProviderInst
}

interface ViewTransition {
  ready: Promise<void>
}

interface Document {
  startViewTransition?: (callback: () => Promise<void> | void) => ViewTransition
}

interface ImportMeta {
  readonly env: Env.ImportMeta
}

/** Build time of the project */
declare const BUILD_TIME: string

declare module "pdfjs-dist/legacy/build/pdf.min.mjs" {
  export * from "pdfjs-dist"
}

declare module "pdfjs-dist/legacy/build/pdf.worker.entry" {
  const entry: string
  export default entry
}

declare module "pdfjs-dist/legacy/web/pdf_viewer.component" {
  export * from "pdfjs-dist/types/web/event_utils"
}

declare module "pdfjs-dist/legacy/web/pdf_viewer" {
  export * from "pdfjs-dist/types/web/pdf_viewer"
}

declare module "pdfjs-dist/legacy/web/event_utils" {
  export * from "pdfjs-dist/types/web/pdf_viewer.component"
}

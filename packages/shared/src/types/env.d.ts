/**
 * Namespace Env
 *
 * It is used to declare the type of the import.meta object
 */
declare namespace Env {
  /** Interface for import.meta */
  interface ImportMeta extends ImportMetaEnv {
    /** The back service env */
    readonly VITE_SERVICE_ENV?: App.Service.EnvType
    readonly VITE_SITE_ORIGIN?: string
    readonly VITE_DOCS_URL?: string
    /** The prefix of the iconify icon */
    readonly VITE_ICON_PREFIX: "icon"
    /**
     * The prefix of the local icon
     *
     * This prefix is start with the icon prefix
     */
    readonly VITE_ICON_LOCAL_PREFIX: "icon-local"
    readonly VITE_ICON_SHARED_PREFIX: "icon-shared"
  }
}

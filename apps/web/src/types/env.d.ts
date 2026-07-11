/// <reference types="@airalogy/shared/src/types/env.d.ts" />

/**
 * Namespace Env
 *
 * It is used to declare the type of the import.meta object
 */
declare namespace Env {
  /** Service environment type */
  type ServiceEnv = "dev" | "prod"

  /** Interface for import.meta */
  interface ImportMeta extends ImportMetaEnv {
    /**
     * Service environment (set via npm scripts)
     * - dev: Local development
     * - prod: Self-hosted production
     */
    readonly VITE_SERVICE_ENV?: ServiceEnv
    /**
     * Whether to enable the http proxy (set via npm scripts)
     *
     * Only valid in the development environment
     */
    readonly VITE_HTTP_PROXY?: CommonType.YesOrNo
    readonly VITE_API_BASE_URL?: string
    readonly VITE_DEMO_BASE_URL?: string
    readonly VITE_MINIO_BASE_URL?: string
    readonly VITE_SITE_ORIGIN?: string
    readonly VITE_OSS_PROXY_TARGET?: string
    readonly VITE_DOCS_URL?: string
    readonly VITE_CHINA_COMPLIANCE_FOOTER?: CommonType.YesOrNo
    readonly VITE_ICP_RECORD_NUMBER?: string
    readonly VITE_ICP_RECORD_URL?: string
    readonly VITE_POLICE_RECORD_NUMBER?: string
    readonly VITE_POLICE_RECORD_CODE?: string
    readonly VITE_POLICE_RECORD_URL?: string
    readonly VITE_POLICE_RECORD_ICON_URL?: string
    readonly VITE_MKCERT?: CommonType.YesOrNo
    /**
     * Record delete grace period in days (frontend display logic)
     */
    readonly VITE_RECORD_DELETE_GRACE_DAYS?: string
    readonly VITE_DEPLOYMENT_MODE?: "community" | "single_lab"
  }
}

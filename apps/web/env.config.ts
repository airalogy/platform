const LOCAL_API_BASE_URL = "http://127.0.0.1:4000"
const LOCAL_DEMO_BASE_URL = "http://127.0.0.1:9528"
const LOCAL_MINIO_BASE_URL = "http://127.0.0.1:9200"

function optionalEnv(value: string | undefined, fallback: string) {
  return value?.trim() || fallback
}

export function createSiteOrigin(env: Pick<Env.ImportMeta, "VITE_SITE_ORIGIN">) {
  return optionalEnv(env.VITE_SITE_ORIGIN, "http://localhost:3000")
}

/**
 * Create service config by current env
 *
 * @param env The current env
 *
 * Environment options:
 * - dev: Local development environment
 * - prod: Self-hosted production environment
 *
 * Quick switch:
 * 1. Use `pnpm dev` for local development.
 * 2. Use VITE_API_BASE_URL to point to a custom backend.
 */
export function createServiceConfig(env: Env.ImportMeta) {
  const { VITE_SERVICE_ENV = "dev", VITE_HTTP_PROXY } = env
  const isHttpProxy = VITE_HTTP_PROXY === "Y"
  const apiBaseURL = optionalEnv(
    env.VITE_API_BASE_URL,
    VITE_SERVICE_ENV === "prod" ? "/api" : LOCAL_API_BASE_URL,
  )
  const demoBaseURL = optionalEnv(env.VITE_DEMO_BASE_URL, LOCAL_DEMO_BASE_URL)
  const minioBaseURL = optionalEnv(env.VITE_MINIO_BASE_URL, LOCAL_MINIO_BASE_URL)

  const serviceConfigMap: App.Service.ServiceConfigMap = {
    dev: {
      baseURL: isHttpProxy ? apiBaseURL : "/api",
      otherBaseURL: {
        demo: demoBaseURL,
        minio: minioBaseURL,
      },
    },
    prod: {
      baseURL: isHttpProxy ? apiBaseURL : "/api",
      otherBaseURL: {
        demo: demoBaseURL,
        minio: minioBaseURL,
      },
    },
  }

  const config = serviceConfigMap[VITE_SERVICE_ENV] ?? serviceConfigMap.dev

  console.log(`[Service Config] Environment: ${VITE_SERVICE_ENV}`)
  console.log(`[Service Config] HTTP Proxy: ${VITE_HTTP_PROXY}`)
  console.log(`[Service Config] Base URL: ${config.baseURL}`)

  return config
}

/**
 * Get proxy pattern of service url
 *
 * @param base The proxy base path
 * @param path The nested request path
 */
export function createProxyPattern(base?: string, path?: string) {
  if (base) {
    if (path) {
      return `${base}${base.endsWith("/") ? "" : "/"}${path}`
    }

    return base
  }

  return "/api"
}

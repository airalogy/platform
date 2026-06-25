import type { ProxyOptions } from "vite"
import { ProxyAgent } from "proxy-agent"

import { createProxyPattern, createServiceConfig } from "../../env.config"

/** Base URL for the application */
const BASE_URL = "/"

const LOCAL_PROXY_HOSTS = new Set([
  "127.0.0.1",
  "::1",
  "0.0.0.0",
  "localhost",
  "host.docker.internal",
])

function shouldBypassOutboundProxy(target: string) {
  try {
    const { hostname } = new URL(target)
    return LOCAL_PROXY_HOSTS.has(hostname) || hostname.endsWith(".local")
  }
  catch {
    return true
  }
}

function createProxyAgent(target: string) {
  return shouldBypassOutboundProxy(target) ? undefined : new ProxyAgent()
}

/**
 * Set http proxy
 *
 * @param env - The current env
 */
export function createViteProxy(env: Env.ImportMeta) {
  const isEnableHttpProxy = env.VITE_HTTP_PROXY === "Y"

  if (!isEnableHttpProxy)
    return undefined

  const { baseURL, otherBaseURL } = createServiceConfig(env)

  const defaultProxyPattern = createProxyPattern(BASE_URL, "api")

  if (!defaultProxyPattern) {
    return undefined
  }

  const proxy: Record<string, ProxyOptions> = {
    [defaultProxyPattern]: {
      target: baseURL,
      changeOrigin: true,
      secure: false,
      rewrite: path => path.replace(new RegExp(`^${defaultProxyPattern}`), ""),
      agent: createProxyAgent(baseURL),
    },
  }

  const otherURLEntries = Object.entries(otherBaseURL)

  for (const [key, url] of otherURLEntries) {
    const proxyPattern = createProxyPattern(BASE_URL, key as App.Service.OtherBaseURLKey)

    proxy[proxyPattern] = {
      target: url,
      secure: false,
      changeOrigin: true,
      rewrite: path => path.replace(new RegExp(`^${proxyPattern}`), ""),
      agent: createProxyAgent(url),
    }
  }

  if (env.VITE_OSS_PROXY_TARGET) {
    proxy["/oss-proxy"] = {
      target: env.VITE_OSS_PROXY_TARGET,
      changeOrigin: true,
      secure: false,
      rewrite: path => path.replace(/^\/oss-proxy/, ""),
      agent: createProxyAgent(env.VITE_OSS_PROXY_TARGET),
    }
  }

  return proxy
}

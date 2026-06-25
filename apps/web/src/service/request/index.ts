import type { AxiosError } from "axios"
import { handleUnauthorized } from "@/utils/auth/unauthorized"
import { createFlatRequest } from "@/utils/axios"
import { localStg } from "@/utils/storage"
import { renderMessageContent } from "@airalogy/composables"
// @ts-expect-error - env.config is built separately in tsconfig.node.json
import { createProxyPattern, createServiceConfig } from "../../../env.config"

const { baseURL: rawBaseURL } = createServiceConfig(import.meta.env as Env.ImportMeta)

const isHttpProxy = import.meta.env.VITE_HTTP_PROXY === "Y"

export const baseURL = isHttpProxy ? createProxyPattern() : rawBaseURL

export const request = createFlatRequest<App.Service.Response>(
  {
    baseURL,
    headers: {},
  },
  {
    onRequest(config) {
      const { headers } = config

      // set token
      const token = localStg.get("token")
      Object.assign(headers, { "Auth-Token": token })

      return config
    },
    isBackendSuccess(response) {
      // when the backend response code is "200", it means the request is success
      // you can change this logic by yourself
      // return response.data.code === "200"
      return response.status === 200 || response.status === 304
    },
    async onBackendFail(_response) {
      // when the backend response code is not 200, it means the request is fail
      // for example: the token is expired, refetch token and retry request
    },
    transformBackendResponse(response) {
      return response.data
    },
    onError(error: AxiosError, cancelAllRequest) {
      // Only handle unauthorized and POST errors here, all other errors will be handled by onMaxRetryTimesExceeded
      if (error.response?.status === 401) {
        cancelAllRequest()
        handleUnauthorized()
      }

      if (error.code === "ERR_CANCELED") {
        return
      }
      const { showError = true, errorClosable = true } = error.config?.metadata || {}

      const method = error.config?.method?.toUpperCase()
      if (showError && (method === "POST" || method === "PUT" || method === "DELETE")) {
        const errorInfo = error.response as unknown as App.Service.Response<{ detail: string }>
        const message = errorInfo?.data.detail || error.message
        window.$message?.error(renderMessageContent(typeof message === "string" ? message : JSON.stringify(message, null, 2)), { duration: errorClosable ? 2000 : 0, closable: true })
      }
    },
  },
)

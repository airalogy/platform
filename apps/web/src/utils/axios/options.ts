import type { AxiosError, CreateAxiosDefaults } from "axios"
import type { IAxiosRetryConfig } from "axios-retry"
import type { RequestOption } from "./request"
import { stringify } from "qs"
import { isHttpSuccess } from "./shared"

export function createDefaultOptions<ResponseData = any>(
  options?: Partial<RequestOption<ResponseData>>,
) {
  const opts: RequestOption<ResponseData> = {
    onRequest: async config => config,
    isBackendSuccess: _response => true,
    onBackendFail: async () => { },
    transformBackendResponse: async response => response.data,
    onError: async () => { },
  }

  Object.assign(opts, options)

  return opts
}

export function createRetryOptions(config?: Partial<CreateAxiosDefaults>) {
  const retryConfig: IAxiosRetryConfig = {
    retries: 3,
    retryDelay: retryCount => retryCount * 500,
    retryCondition: (error) => {
      const { config, response } = error as AxiosError
      if (!config || !response) {
        return false
      }
      const { method, metadata } = config
      if (metadata?.noRetry || (method || "").toUpperCase() !== "GET") {
        return false
      }

      const { status, data } = response
      return status !== 500
        && status !== 401
        && status !== 403
        && status !== 404
        && status !== 422
        && (status !== 400
          || (data as { detail: string })?.detail !== "NoResultFound('No row was found when one was required')")
    },
    onMaxRetryTimesExceeded: (error) => {
      // Ignore canceled requests
      if (error.code === "ERR_CANCELED") {
        return
      }

      const { showError = true } = error.config?.metadata || {}
      const errorInfo = error.response as unknown as App.Service.Response<{ detail: string }>
      const message = errorInfo?.data.detail || error.message
      if (showError && window.$message && message) {
        if (typeof message === "object") {
          window.$message.error(JSON.stringify(message, null, 2), {
            closable: true,
            duration: 0,
          })
        }
        else {
          window.$message.error(message, {
            closable: true,
          })
        }
      }
    },
  }

  Object.assign(retryConfig, config)

  return retryConfig
}

export function createAxiosConfig(config?: Partial<CreateAxiosDefaults>) {
  const TEN_SECONDS = 10 * 1000

  const axiosConfig: CreateAxiosDefaults = {
    timeout: TEN_SECONDS,
    headers: {
      "Content-Type": "application/json",
    },
    validateStatus: isHttpSuccess,
    paramsSerializer: (params) => {
      return stringify(params, { arrayFormat: "comma", skipNulls: true })
    },
  }

  Object.assign(axiosConfig, config)

  return axiosConfig
}

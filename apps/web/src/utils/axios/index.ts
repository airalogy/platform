import type {
  AxiosResponse,
  CreateAxiosDefaults,
  InternalAxiosRequestConfig,
} from "axios"
import type {
  CustomAxiosRequestConfig,
  FlatRequestInstance,
  MappedType,
  RequestInstance,
  RequestOption,
  ResponseType,
} from "./request"
import axios, { AxiosError } from "axios"
import axiosRetry from "axios-retry"
import { nanoid } from "nanoid"
import { BACKEND_ERROR_CODE, REQUEST_ID_KEY } from "./constant"
import { createAxiosConfig, createDefaultOptions, createRetryOptions } from "./options"
import { newAbortSignal } from "./shared"

function createCommonRequest<ResponseData = any>(
  axiosConfig?: CreateAxiosDefaults,
  options?: Partial<RequestOption<ResponseData>>,
) {
  const opts = createDefaultOptions<ResponseData>(options)

  const axiosConf = createAxiosConfig(axiosConfig)
  const instance = axios.create(axiosConf)

  const cancelControllerMap = new Map<string, AbortController>()

  // config axios retry
  const retryOptions = createRetryOptions(axiosConf)
  axiosRetry(instance, retryOptions)

  instance.interceptors.request.use((conf) => {
    const config: InternalAxiosRequestConfig = { ...conf }
    // set request id
    const requestId = conf.metadata?.requestId || nanoid()
    config.headers.set(REQUEST_ID_KEY, requestId)

    // config cancel token
    const { signal: cancelSignal, controller: cancelController } = newAbortSignal()
    config.signal = cancelSignal
    cancelControllerMap.set(requestId, cancelController)

    // handle config by hook
    const handledConfig = opts.onRequest?.(config) || config

    return handledConfig
  })

  instance.interceptors.response.use(
    async (response) => {
      if (opts.isBackendSuccess(response)) {
        return Promise.resolve(response)
      }

      const fail = await opts.onBackendFail(response, instance)
      if (fail) {
        return fail
      }

      const backendError = new AxiosError<ResponseData>(
        "the backend request error",
        BACKEND_ERROR_CODE,
        response.config,
        response,
        response.request,
      )

      await opts.onError(backendError, cancelAllRequest)

      return Promise.reject(backendError)
    },
    async (error: AxiosError<ResponseData>) => {
      await opts.onError(error, cancelAllRequest)

      return Promise.reject(error)
    },
  )

  function cancelRequest(requestId: string) {
    const cancelController = cancelControllerMap.get(requestId)
    if (cancelController) {
      cancelController.abort()
      cancelControllerMap.delete(requestId)
    }
  }

  function cancelAllRequest() {
    cancelControllerMap.forEach((cancelController) => {
      cancelController.abort()
    })
    cancelControllerMap.clear()
  }

  return {
    instance,
    opts,
    cancelRequest,
    cancelAllRequest,
  }
}

/**
 * create a request instance
 *
 * @param axiosConfig axios config
 * @param options request options
 */
export function createRequest<ResponseData = any>(
  axiosConfig?: CreateAxiosDefaults,
  options?: Partial<RequestOption<ResponseData>>,
) {
  const { instance, opts, cancelRequest, cancelAllRequest } = createCommonRequest<ResponseData>(
    axiosConfig,
    options,
  )

  const request: RequestInstance = async function request<T = any, R extends ResponseType = "json">(
    config: CustomAxiosRequestConfig,
  ) {
    const response: AxiosResponse<ResponseData> = await instance(config)

    const responseType = response.config?.responseType || "json"

    if (responseType === "json") {
      return opts.transformBackendResponse(response)
    }

    return response.data as MappedType<R, T>
  } as RequestInstance

  request.cancelRequest = cancelRequest
  request.cancelAllRequest = cancelAllRequest

  return request
}

/**
 * create a flat request instance
 *
 * The response data is a flat object: { data: any, error: AxiosError }
 *
 * @param axiosConfig axios config
 * @param options request options
 */
export function createFlatRequest<ResponseData = any>(
  axiosConfig?: CreateAxiosDefaults,
  options?: Partial<RequestOption<ResponseData>>,
) {
  const { instance, opts, cancelRequest, cancelAllRequest } = createCommonRequest<ResponseData>(
    axiosConfig,
    options,
  )

  const flatRequest: FlatRequestInstance = async function flatRequest<
    T = any,
    R extends ResponseType = "json",
  >(config: CustomAxiosRequestConfig) {
    try {
      const response: AxiosResponse<ResponseData> = await instance(config)

      const responseType = response.config?.responseType || "json"

      if (responseType === "json") {
        const data = opts.transformBackendResponse(response)

        return { data, error: null }
      }

      return { data: response.data as MappedType<R, T>, error: null }
    }
    catch (error) {
      return { data: null, error }
    }
  } as FlatRequestInstance

  flatRequest.cancelRequest = cancelRequest
  flatRequest.cancelAllRequest = cancelAllRequest

  return flatRequest
}

/**
 * Creates a request instance specifically configured for handling streaming responses
 */
export function createStreamRequest<ResponseData = any>(
  axiosConfig?: CreateAxiosDefaults,
  options?: Partial<RequestOption<ResponseData>>,
) {
  // Merge the provided config with stream-specific defaults
  const streamConfig: CreateAxiosDefaults = {
    ...axiosConfig,
    responseType: "stream",
  }

  // Set up the common request with stream handling
  const { instance, opts, cancelRequest, cancelAllRequest } = createCommonRequest<ResponseData>(
    streamConfig,
    options,
  )

  const streamRequest: RequestInstance = async function request<T = any>(
    config: CustomAxiosRequestConfig,
  ) {
    // Ensure responseType is set to stream for this request

    // Get the response
    const response: AxiosResponse<ResponseData> = await instance(config)

    // For streams, we usually want to return the raw stream data
    // but still allow custom transformation if provided
    if (opts.transformBackendResponse) {
      return opts.transformBackendResponse(response)
    }

    // Default: return the raw response data (which should be a stream)
    return response.data as unknown as T
  } as RequestInstance

  streamRequest.cancelRequest = cancelRequest
  streamRequest.cancelAllRequest = cancelAllRequest

  return streamRequest
}

export { BACKEND_ERROR_CODE, REQUEST_ID_KEY }
export type * from "./request"
export type { AxiosError, CreateAxiosDefaults }

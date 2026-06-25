import type {
  AxiosError,
  CreateAxiosDefaults,
  CustomAxiosRequestConfig,
  MappedType,
  RequestOption,
  ResponseType,
} from "@/utils/axios"
import type { Ref } from "vue"
import { createFlatRequest } from "@/utils/axios"
import { useLoading } from "@airalogy/composables"
import { onUnmounted, ref } from "vue"

export interface HookRequestInstanceResponseSuccessData<T = any> {
  data: Ref<T>
  error: Ref<null>
}

export interface HookRequestInstanceResponseFailData<T = any> {
  data: Ref<null>
  error: Ref<AxiosError<T>>
}

export type HookRequestInstanceResponseData<T = any> = {
  loading: Ref<boolean>
} & (HookRequestInstanceResponseSuccessData<T> | HookRequestInstanceResponseFailData<T>)

export interface HookRequestInstance {
  <T = any, R extends ResponseType = "json">(
    config: CustomAxiosRequestConfig,
  ): HookRequestInstanceResponseData<MappedType<R, T>>
  cancelRequest: (requestId: string) => void
  cancelAllRequest: () => void
}

/**
 * create a hook request instance
 *
 * @param axiosConfig
 * @param options
 */
export function createHookRequest<ResponseData = any>(
  axiosConfig?: CreateAxiosDefaults,
  options?: Partial<RequestOption<ResponseData>>,
) {
  const request = createFlatRequest<ResponseData>(axiosConfig, options)

  const hookRequest: HookRequestInstance = function hookRequest<
    T = any,
    R extends ResponseType = "json",
  >(config: CustomAxiosRequestConfig) {
    const { loading, startLoading, endLoading } = useLoading()

    const data = ref<MappedType<R, T> | null>(null)
    const error = ref<AxiosError<MappedType<R, T>> | null>(null)

    startLoading()

    // Cancel any pending requests when component unmounts
    onUnmounted(() => {
      request.cancelAllRequest()
    })

    request(config).then((res) => {
      if (res.data) {
        data.value = res.data
      }
      else {
        error.value = res.error
      }

      endLoading()
    })

    return {
      loading,
      data,
      error,
    }
  } as HookRequestInstance

  hookRequest.cancelRequest = request.cancelRequest
  hookRequest.cancelAllRequest = request.cancelAllRequest

  return hookRequest
}

import type { ToRefs } from "vue"
import type { ChatProviderContext } from "../providers/useChatProvider"
import type { ChatAPI, IProps } from "./types"

export function useChatAPI(provider: ChatProviderContext, props: ToRefs<IProps>): ChatAPI {
  const { baseUrl, token, stopStream: stopStreamRef } = provider

  const endpoint = computed(() => `${baseUrl?.value}/qa/message`)
  const fieldInputEndpoint = computed(() => `${baseUrl?.value}/field_input/message`)
  const sttEndpoint = computed(() => `${baseUrl?.value}/stt/message`)

  async function stopStream(payload: { chatId: string }) {
    return await stopStreamRef?.value?.(payload)
  }

  return {
    fieldInputEndpoint,
    sttEndpoint,
    endpoint,
    token,
    baseUrl,
    stopStream,
  } as ChatAPI
}

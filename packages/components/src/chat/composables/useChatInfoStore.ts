import type { ToRefs } from "vue"
import type { ChatProviderProps } from "../providers/useChatProvider"
import type { IEmits, IProps } from "./types"
import { createInjectionState } from "@vueuse/core"
import { onUnmounted } from "vue"
import { useChatProvider } from "../providers/useChatProvider"
import { useAudioRecorder } from "./useAudioRecorder"
import { useChatAPI } from "./useChatAPI"
import { useChatEventHandlers } from "./useChatEventHandlers"
import { useChatHandlers } from "./useChatHandlers"
import { useChatHistory } from "./useChatHistory"
import { useChatMutations } from "./useChatMutations"
import { useChatSessionNavigation } from "./useChatSessionNavigation"
import { useChatState } from "./useChatState"
import { useChatStream } from "./useChatStream"
import { useFileUpload } from "./useFileUpload"

export type { IProps }

const [useProvideChatInfoStore, useChatInfoStore] = createInjectionState((props: ToRefs<IProps>, emit: IEmits) => {
  const providerContext = useChatProvider()
  const { postToolResultChat, mode } = providerContext
  // Initialize all composable states and functionality
  const state = useChatState(props, providerContext.enabledModels)
  const mutations = useChatMutations(state, providerContext as unknown as ChatProviderProps)
  const stream = useChatStream(state, scrollToBottom, postToolResultChat, providerContext)
  const navigation = useChatSessionNavigation(state)

  const api = useChatAPI(providerContext, props)
  const handlers = useChatHandlers({ state, mutations, stream, scrollToBottom, navigation, api, provider: providerContext })
  const history = useChatHistory(state)
  const fileUpload = useFileUpload(state, providerContext)

  // Audio recording functionality
  const {
    audioRecorder,
    isRecording,
    isSupported,
    startRecording: startAudioRecording,
    stopRecording: stopAudioRecording,
    resetAudioRecorder,
    startDurationCounter,
    stopDurationCounter,
  } = useAudioRecorder()

  /**
   * Emit scroll event to parent
   * @param smart - true for smart scroll (only if near bottom), false/undefined for force scroll
   */
  async function scrollToBottom(smart?: boolean) {
    emit("scrollToBottom", smart)
  }

  // Audio recording wrapper functions
  async function startRecording() {
    await startAudioRecording()
    state.inputMethod.value = "audio"
  }

  async function stopRecording() {
    await stopAudioRecording()
    // state.inputMethod.value = "text"
  }

  useChatEventHandlers(state, mutations, history, mode, providerContext)

  onUnmounted(() => {
    stopDurationCounter()
    resetAudioRecorder()
  })

  return {
    ...providerContext,
    ...state,

    // Core Chat Actions
    ...handlers,
    ...mutations,
    ...history,
    ...fileUpload,
    ...navigation,

    // API
    ...api,

    // UI State
    audioRecorder,
    isRecording,
    isSupported,

    // Audio Recording Actions
    startRecording,
    stopRecording,
    resetAudioRecorder,
    startDurationCounter,
    stopDurationCounter,
  }
})

function useOrProvideChatInfoStore(props: ToRefs<IProps>, emit: IEmits) {
  try {
    const store = useChatInfoStore()
    if (!store) {
      throw new Error("Chat info store not found")
    }
    return store
  }
  catch (error) {
    // No parent provider found, create a new one
    return useProvideChatInfoStore(props, emit)
  }
}

export { useChatInfoStore, useOrProvideChatInfoStore, useProvideChatInfoStore }

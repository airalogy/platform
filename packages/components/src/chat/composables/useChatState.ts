import type { SelectOption } from "naive-ui"
import type { ToRefs } from "vue"
import type { ChatController, ChatState, InputMethod, IProps } from "./types"
import { useLoading } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { ChatModel, ChatType } from "@airalogy/shared/enum/chat"
import { nanoid } from "nanoid"
import { computed, ref, watch } from "vue"
// import { useAuthStore } from "../../store/modules/auth"
import { useChatStore } from "../store"

const modelOptionDefs = [
  { labelKey: "chat.model.gpt", value: ChatModel.GPT, key: "gpt", requiredLevel: 3 },
  { labelKey: "chat.model.pro", value: ChatModel.PRO, key: "pro", requiredLevel: 3 },
  { labelKey: "chat.model.plus", value: ChatModel.PLUS, key: "plus", requiredLevel: 2 },
  { labelKey: "chat.model.basic", value: ChatModel.BASIC, key: "basic", requiredLevel: 1 },
] as const

export function useChatState(props: ToRefs<IProps>): ChatState {
  const { chatId: defaultChatId, source: sourceRef, role: roleRef, level: levelRef } = props as ToRefs<Required<IProps>>
  const hubSearchDefault = props.hubSearchDefault ?? ref(false)
  const airalogyId = props.airalogyId || ref(null)
  const chatStore = useChatStore()
  // const userInfo = useAuthStore()
  const { loading, startLoading, endLoading } = useLoading()
  // Core state
  const chatId = computed(() => chatStore.state.active)
  const prompt = ref<string>("")
  const emptyDraftId = ref<string | null>(nanoid())
  const session = computed(() => chatStore.findSessionByUUID())
  const messageList = ref<Chat.ChatMessage[]>([])
  const messageCount = ref<number>(0)

  // Model and role configuration
  const selectedRole = ref<ChatType>(toValue(roleRef) || ChatType.NORMAL)
  const selectedModel = ref<ChatModel>(ChatModel.BASIC)
  const deepResearch = ref<boolean>(false)
  const enableThinking = ref<boolean>(false)
  const enableSearch = ref<boolean>(false)
  const enableHubSearch = ref<boolean>(Boolean(toValue(hubSearchDefault)))

  // UI state
  const inputMethod = ref<InputMethod>("text")
  const controller = ref<ChatController | null>(null)
  const audioBase64 = ref<string | null>(null)

  // Computed properties
  const isEmptyDraft = computed(() => chatId.value === emptyDraftId.value)

  const context = computed(() => {
    if (isEmptyDraft.value && emptyDraftId.value) {
      return chatStore.getDraftMessage(emptyDraftId.value)?.context || null
    }
    return chatId.value ? chatStore.context[chatId.value] || null : null
  })

  const source = computed(() => sourceRef.value || session.value?.source || "global")

  watch(
    () => toValue(hubSearchDefault),
    (val) => {
      enableHubSearch.value = Boolean(val)
    },
    { immediate: true },
  )

  const history = computed(() => chatStore.getTargetHistory(source.value, airalogyId.value))

  const allHistoryRecord = computed((): Record<Chat.ChatSource, Chat.ChatHistory[]> => {
    if (!airalogyId.value) {
      const currentSource = source.value || "global"
      const list = chatStore.getHistoryBySource(currentSource) || []

      return { [currentSource]: list } as unknown as Record<Chat.ChatSource, Chat.ChatHistory[]>
    }

    const list = chatStore.getHistoryByAiralogyId(airalogyId.value)

    if (list.length === 0) {
      const currentSource = source.value || "global"
      return { [currentSource]: [] } as any as Record<Chat.ChatSource, Chat.ChatHistory[]>
    }

    return list.reduce(
      (acc: Record<Chat.ChatSource, Chat.ChatHistory[]>, item: Chat.ChatHistory) => {
        const { source } = item
        if (!acc[source]) {
          acc[source] = []
        }
        acc[source].push(item)
        return acc
      },
      {} as Record<Chat.ChatSource, Chat.ChatHistory[]>,
    )
  })

  const modelOptions = computed<SelectOption[]>(() => {
    const level = toValue(levelRef) ?? 3 // Default to highest permission level, showing all options
    return modelOptionDefs
      .filter(item => level >= item.requiredLevel)
      .map(item => ({
        label: $t(item.labelKey),
        value: item.value,
        key: item.key,
      }))
  })

  const modelName = computed(() => {
    const option = modelOptionDefs.find(opt => opt.value === selectedModel.value)
    return option ? $t(option.labelKey) : $t("chat.model.select")
  })

  const roleName = computed(() => {
    const roleMap: Record<ChatType, string> = {
      [ChatType.NORMAL]: "Normal",
      [ChatType.FIELD_INPUT]: "Field Input",
      [ChatType.RECORDS]: "Records",
      [ChatType.VISION]: "Vision",
      [ChatType.STT]: "STT",
    }
    return roleMap[selectedRole.value]
  })

  const conversationList = computed(
    () => {
      const { data } = session.value || {}
      if (!data) {
        return []
      }

      return data.filter(item => !item.inversion && Boolean(item.conversationOptions))
    },
  )

  const attachments = computed(() => {
    const currentChatId = chatId.value || emptyDraftId.value
    if (!currentChatId) {
      return null
    }
    return chatStore.getMessageAttachments(currentChatId)
  })

  return {
    // Core state
    chatId,
    session,
    prompt,
    emptyDraftId,
    messageList,
    messageCount,

    // Model and role state
    selectedRole,
    selectedModel,
    deepResearch,
    enableThinking,
    enableSearch,
    enableHubSearch,

    // UI state
    inputMethod,
    controller,
    audioBase64,

    // Loading state
    loading,
    startLoading,
    endLoading,

    // Computed properties
    isEmptyDraft,
    context,
    source,
    history,
    allHistoryRecord,
    modelOptions,
    modelName,
    roleName,
    conversationList,
    attachments,

    // Store references
    chatStore,

    // Props references
    defaultChatId,
    airalogyId,
    sourceRef,
    roleRef,
  }
}
